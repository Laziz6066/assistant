# ollama LLM Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-LLM fallback (`LLMFallbackRouter` wrapping `RulesRouter`) so that when rules return `Intent.unknown()` the assistant asks `qwen2.5:3b-instruct` via ollama to classify the utterance into a known intent and slot set; on any LLM failure the user just gets the existing "Не понял, повтори" response.

**Architecture:** `LLMFallbackRouter(NLURouter)` wraps a primary `NLURouter` (the existing `RulesRouter`). If the primary returns a known intent, the LLM never runs. Otherwise, `OllamaClient` calls ollama's chat API with `format="json"`, parses+validates the response (catalog membership, confidence ≥ threshold, slot type coercion), and returns either a valid `Intent` or `Intent.unknown()`. Connection failures cache a 60-second unreachable window; 404 (model not pulled) marks permanent unreachable for the process.

**Tech Stack:** Python 3.11+, ollama-python ≥0.3 (synchronous client), httpx (ollama-python's transport), pydantic v2.

**Depends on:** voice-assistant MVP + Piper TTS at commit `5a0a8bf` or later on branch `worktree-voice-assistant-mvp`. Spec: `docs/superpowers/specs/2026-05-20-ollama-fallback-design.md`.

---

## File Structure

**New files:**
- `src/voice_assistant/nlu/prompt.py` — `_load_catalog(commands_path)` + `build_system_prompt(catalog, aliases)`
- `src/voice_assistant/nlu/parse.py` — `parse_and_validate(content, catalog, min_confidence) -> Intent` pure function
- `src/voice_assistant/nlu/ollama_client.py` — `OllamaClient` class (chat call + unreachable cache + exception → unknown mapping)
- `src/voice_assistant/nlu/llm_fallback.py` — `LLMFallbackRouter(NLURouter)`

**Modified files:**
- `src/voice_assistant/config.py` — add `LLMConfig` + `AppConfig.llm: LLMConfig`
- `src/voice_assistant/main.py` — `_build` wraps `RulesRouter` in `LLMFallbackRouter` when `cfg.llm.enabled`
- `config/default.yaml` — add `llm` section
- `pyproject.toml` — add `ollama>=0.3` dep
- `README.md` — append LLM Fallback setup section + manual checklist additions

**New tests:**
- `tests/unit/nlu/test_prompt.py`
- `tests/unit/nlu/test_parse.py`
- `tests/unit/nlu/test_ollama_client.py`
- `tests/unit/nlu/test_llm_fallback.py`
- `tests/unit/test_config.py` — extend with LLMConfig tests
- `tests/unit/test_main.py` — extend with one `_build` test for LLM wiring

---

## Task 1: `LLMConfig` in `config.py`

**Files:**
- Modify: `src/voice_assistant/config.py`
- Test: extend `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py`:

```python
from voice_assistant.config import LLMConfig


def test_llm_config_default_values():
    cfg = LLMConfig()
    assert cfg.enabled is False
    assert cfg.model == "qwen2.5:3b-instruct"
    assert cfg.host == "http://localhost:11434"
    assert cfg.timeout_s == 3.0
    assert cfg.temperature == 0.1
    assert cfg.min_confidence == 0.5


def test_llm_config_accepts_overrides():
    cfg = LLMConfig(enabled=True, model="llama3.2:3b",
                    timeout_s=5.0, min_confidence=0.7)
    assert cfg.enabled is True
    assert cfg.model == "llama3.2:3b"
    assert cfg.timeout_s == 5.0
    assert cfg.min_confidence == 0.7


def test_app_config_has_llm_section_with_defaults():
    cfg = AppConfig()
    assert cfg.llm.enabled is False
    assert cfg.llm.model == "qwen2.5:3b-instruct"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v -k llm`
Expected: 3 FAILs with `ImportError: cannot import name 'LLMConfig'`.

- [ ] **Step 3: Add `LLMConfig` and wire into `AppConfig`**

Edit `src/voice_assistant/config.py`. After the existing `TTSConfig` class and before `AppConfig`, insert:

```python
class LLMConfig(BaseModel):
    enabled: bool = False
    model: str = "qwen2.5:3b-instruct"
    host: str = "http://localhost:11434"
    timeout_s: float = 3.0
    temperature: float = 0.1
    min_confidence: float = 0.5
```

Inside `AppConfig`, add the `llm` field (place it after `tts`):

```python
llm: LLMConfig = Field(default_factory=LLMConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v -k llm`
Expected: 3 PASS.

- [ ] **Step 5: Run full config tests + full suite**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v`
Then: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous count + 3.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/config.py tests/unit/test_config.py
git commit -m "feat(config): add LLMConfig for ollama fallback"
```

---

## Task 2: Catalog loader + prompt builder

**Files:**
- Create: `src/voice_assistant/nlu/prompt.py`
- Test: `tests/unit/nlu/test_prompt.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/nlu/test_prompt.py
from pathlib import Path
import pytest
from voice_assistant.nlu.prompt import load_catalog, build_system_prompt


def _write_commands(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "commands.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_catalog_collects_intents_with_slots(tmp_path):
    p = _write_commands(tmp_path,
        '- intent: open_app\n'
        '  examples: ["открой {app}"]\n'
        '  slots: {app: string}\n'
        '- intent: volume_set\n'
        '  examples: ["громкость {level:int}"]\n'
        '  slots: {level: int}\n'
        '- intent: minimize_all\n'
        '  examples: ["сверни всё"]\n'
        '  slots: {}\n')
    catalog = load_catalog(p)
    assert "open_app" in catalog
    assert catalog["open_app"]["slots"] == [("app", "string")]
    assert catalog["volume_set"]["slots"] == [("level", "int")]
    assert catalog["minimize_all"]["slots"] == []


def test_load_catalog_dedupes_intent_across_multiple_examples(tmp_path):
    # If the same intent appears once with the same slots, no duplicate
    p = _write_commands(tmp_path,
        '- intent: open_app\n'
        '  examples: ["открой {app}", "запусти {app}"]\n'
        '  slots: {app: string}\n')
    catalog = load_catalog(p)
    assert list(catalog.keys()) == ["open_app"]
    assert catalog["open_app"]["slots"] == [("app", "string")]


def test_build_system_prompt_lists_every_intent():
    catalog = {
        "open_app":     {"slots": [("app", "string")]},
        "minimize_all": {"slots": []},
        "volume_set":   {"slots": [("level", "int")]},
    }
    prompt = build_system_prompt(catalog, app_aliases={})
    assert "open_app" in prompt
    assert "minimize_all" in prompt
    assert "volume_set" in prompt
    # int slot type annotated
    assert "int" in prompt
    # JSON contract present
    assert '"intent"' in prompt
    assert '"slots"' in prompt
    assert '"confidence"' in prompt
    # Unknown-fallback rule present
    assert "unknown" in prompt.lower()


def test_build_system_prompt_includes_aliases_when_present():
    catalog = {"open_app": {"slots": [("app", "string")]}}
    prompt = build_system_prompt(catalog,
                                  app_aliases={"телега": "telegram",
                                               "браузер": "chrome"})
    assert "телега" in prompt
    assert "telegram" in prompt
    assert "браузер" in prompt
    assert "chrome" in prompt


def test_build_system_prompt_omits_alias_block_when_empty():
    catalog = {"open_app": {"slots": [("app", "string")]}}
    prompt = build_system_prompt(catalog, app_aliases={})
    # No alias section should appear
    assert "Алиасы" not in prompt and "alias" not in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_prompt.py -v`
Expected: 5 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `prompt.py`**

Create `src/voice_assistant/nlu/prompt.py`:

```python
from __future__ import annotations
from pathlib import Path
import yaml


def load_catalog(commands_path: Path | str) -> dict[str, dict]:
    """Load commands.yaml into a flat catalog: intent_name -> {slots: [(name, type), ...]}.

    Duplicates of the same intent across multiple yaml entries are collapsed —
    first occurrence wins (matching RulesRouter behaviour).
    """
    raw = yaml.safe_load(Path(commands_path).read_text(encoding="utf-8")) or []
    catalog: dict[str, dict] = {}
    for entry in raw:
        name = entry["intent"]
        if name in catalog:
            continue
        slots_field = entry.get("slots") or {}
        slots = [(k, v) for k, v in slots_field.items()]
        catalog[name] = {"slots": slots}
    return catalog


def _format_intent_line(name: str, slots: list[tuple[str, str]]) -> str:
    if not slots:
        return f"- {name} — без slots."
    slot_descs = ", ".join(f"{n} ({t})" for n, t in slots)
    return f"- {name} — slots: {slot_descs}."


def build_system_prompt(catalog: dict[str, dict],
                         app_aliases: dict[str, str]) -> str:
    """Assemble the system prompt from the live catalog.

    The intent list is generated from `catalog`; aliases are appended when
    non-empty. Keep examples static — they're crafted to teach the model the
    JSON contract.
    """
    intent_lines = "\n".join(_format_intent_line(n, c["slots"])
                              for n, c in catalog.items())

    alias_block = ""
    if app_aliases:
        pairs = ", ".join(f"{k}→{v}" for k, v in app_aliases.items())
        alias_block = f"\n\nАлиасы приложений: {pairs}"

    return f"""\
Ты — классификатор голосовых команд для ПК-ассистента. Пользователь говорит фразу на русском, ты определяешь намерение и параметры.

Доступные намерения (intents):
{intent_lines}{alias_block}

Правила:
1. Отвечай ТОЛЬКО валидным JSON в формате: {{"intent": "<name>", "slots": {{}}, "confidence": <0.0-1.0>}}
2. Если фраза не подходит ни под один intent — верни {{"intent": "unknown", "slots": {{}}, "confidence": 0.0}}
3. Confidence ≥ 0.7 если уверен, иначе ниже
4. Слот app/name/query: извлеки самое короткое осмысленное значение
5. Не добавляй лишних полей, не пиши пояснений

Примеры:
"запусти мне телегу пожалуйста" → {{"intent":"open_app","slots":{{"app":"telegram"}},"confidence":0.9}}
"скинь окошко вниз" → {{"intent":"minimize_all","slots":{{}},"confidence":0.85}}
"что в буфере" → {{"intent":"clipboard_read","slots":{{}},"confidence":0.9}}
"закрой эту хрень" → {{"intent":"close_window","slots":{{}},"confidence":0.75}}
"расскажи анекдот" → {{"intent":"unknown","slots":{{}},"confidence":0.0}}
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_prompt.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 5.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/nlu/prompt.py tests/unit/nlu/test_prompt.py
git commit -m "feat(nlu): catalog loader + system prompt builder for ollama fallback"
```

---

## Task 3: `parse_and_validate` pure function

This is the response validator. Pure function — no I/O, no mocking required. Tests are fast.

**Files:**
- Create: `src/voice_assistant/nlu/parse.py`
- Test: `tests/unit/nlu/test_parse.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/nlu/test_parse.py
from voice_assistant.nlu.parse import parse_and_validate
from voice_assistant.core.types import Intent


_CATALOG = {
    "open_app":     {"slots": [("app", "string")]},
    "volume_set":   {"slots": [("level", "int")]},
    "minimize_all": {"slots": []},
}


def test_parse_valid_open_app():
    content = '{"intent": "open_app", "slots": {"app": "telegram"}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "open_app"
    assert intent.slots == {"app": "telegram"}
    assert abs(intent.confidence - 0.9) < 1e-6


def test_parse_valid_slotless_intent():
    content = '{"intent": "minimize_all", "slots": {}, "confidence": 0.85}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "minimize_all"
    assert intent.slots == {}


def test_parse_int_slot_coerced_from_string():
    content = '{"intent": "volume_set", "slots": {"level": "20"}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "volume_set"
    assert intent.slots == {"level": 20}
    assert isinstance(intent.slots["level"], int)


def test_parse_int_slot_accepts_integer_already():
    content = '{"intent": "volume_set", "slots": {"level": 30}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.slots == {"level": 30}


def test_parse_string_slot_stripped():
    content = '{"intent": "open_app", "slots": {"app": "  telegram  "}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.slots == {"app": "telegram"}


def test_parse_unknown_response_returns_unknown():
    content = '{"intent": "unknown", "slots": {}, "confidence": 0.0}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_invalid_json_returns_unknown():
    intent = parse_and_validate("not json", _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_missing_intent_key_returns_unknown():
    intent = parse_and_validate('{"slots": {}, "confidence": 0.9}',
                                  _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_hallucinated_intent_returns_unknown():
    content = '{"intent": "make_coffee", "slots": {}, "confidence": 0.99}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_low_confidence_returns_unknown():
    content = '{"intent": "open_app", "slots": {"app": "x"}, "confidence": 0.4}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_missing_required_slot_returns_unknown():
    content = '{"intent": "open_app", "slots": {}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_uncoercible_int_slot_returns_unknown():
    content = '{"intent": "volume_set", "slots": {"level": "loud"}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_non_dict_slots_returns_unknown():
    content = '{"intent": "open_app", "slots": "telegram", "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_confidence_at_threshold_accepted():
    content = '{"intent": "minimize_all", "slots": {}, "confidence": 0.5}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "minimize_all"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_parse.py -v`
Expected: 14 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `parse.py`**

Create `src/voice_assistant/nlu/parse.py`:

```python
from __future__ import annotations
import json
from loguru import logger

from voice_assistant.core.types import Intent


def parse_and_validate(content: str, catalog: dict[str, dict],
                       min_confidence: float) -> Intent:
    """Parse an ollama JSON response and validate it against the catalog.

    Returns Intent.unknown() on ANY problem: bad JSON, missing keys, intent
    not in catalog, low confidence, slot type mismatch, missing required slot.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        logger.debug(f"LLM returned non-JSON: {content!r}")
        return Intent.unknown()

    if not isinstance(data, dict):
        logger.debug(f"LLM response not a dict: {content!r}")
        return Intent.unknown()

    intent_name = data.get("intent")
    if not isinstance(intent_name, str):
        logger.debug(f"LLM missing/invalid intent field: {content!r}")
        return Intent.unknown()

    if intent_name == "unknown":
        return Intent.unknown()

    if intent_name not in catalog:
        logger.debug(f"LLM hallucinated intent {intent_name!r}, "
                      f"not in catalog")
        return Intent.unknown()

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        logger.debug(f"LLM invalid confidence: {content!r}")
        return Intent.unknown()

    if confidence < min_confidence:
        return Intent.unknown()

    slots_raw = data.get("slots", {})
    if not isinstance(slots_raw, dict):
        logger.debug(f"LLM slots is not a dict: {content!r}")
        return Intent.unknown()

    declared_slots = catalog[intent_name]["slots"]
    coerced: dict[str, int | str] = {}
    for slot_name, slot_type in declared_slots:
        if slot_name not in slots_raw:
            logger.debug(f"LLM missing required slot {slot_name!r} "
                          f"for intent {intent_name!r}")
            return Intent.unknown()
        raw_val = slots_raw[slot_name]
        if slot_type == "int":
            try:
                coerced[slot_name] = int(raw_val)
            except (TypeError, ValueError):
                logger.debug(f"LLM uncoercible int slot {slot_name!r}: "
                              f"{raw_val!r}")
                return Intent.unknown()
        else:
            coerced[slot_name] = str(raw_val).strip()

    return Intent(name=intent_name, slots=coerced, confidence=confidence)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_parse.py -v`
Expected: 14 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 14.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/nlu/parse.py tests/unit/nlu/test_parse.py
git commit -m "feat(nlu): pure parse_and_validate for LLM JSON responses"
```

---

## Task 4: Dependencies + `config/default.yaml`

This task installs `ollama` and adds the yaml section. Comes before Task 5 (OllamaClient) so the `import ollama` at module level there resolves.

**Files:**
- Modify: `pyproject.toml`
- Modify: `config/default.yaml`

- [ ] **Step 1: Add `ollama` to `pyproject.toml`**

Open `pyproject.toml`. In the `[project] dependencies = [...]` list, add:

```toml
  "ollama>=0.3",
```

- [ ] **Step 2: Add `llm` section to `config/default.yaml`**

Append to `config/default.yaml`:

```yaml
llm:
  enabled: false
  model: qwen2.5:3b-instruct
  host: http://localhost:11434
  timeout_s: 3.0
  temperature: 0.1
  min_confidence: 0.5
```

- [ ] **Step 3: Install + smoke check**

Run from worktree root:
```bash
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -c "import ollama; print(ollama.__version__); import inspect; print(inspect.signature(ollama.Client.chat))"
.\.venv\Scripts\python.exe -c "from voice_assistant.config import load_config; c = load_config('config/default.yaml'); print(c.llm)"
```
Expected:
- ollama version prints (≥ 0.3)
- Chat signature includes `model`, `messages`, `format`, `options`, `keep_alive`
- LLMConfig prints with `enabled=False` and the other defaults from Task 1

If `ollama.__version__` is missing or `inspect.signature(ollama.Client.chat)` fails, report DONE_WITH_CONCERNS so the implementer of Task 5 can adapt.

- [ ] **Step 4: Full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green (no new tests this task).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml config/default.yaml
git commit -m "chore(deps): add ollama>=0.3 + llm section in default.yaml"
```

---

## Task 5: `OllamaClient`

**Files:**
- Create: `src/voice_assistant/nlu/ollama_client.py`
- Test: `tests/unit/nlu/test_ollama_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/nlu/test_ollama_client.py
import time
from unittest.mock import MagicMock, patch
import pytest

from voice_assistant.nlu.ollama_client import OllamaClient
from voice_assistant.core.types import Intent


_CATALOG = {
    "open_app":     {"slots": [("app", "string")]},
    "minimize_all": {"slots": []},
}


def _make_chat_response(content: str):
    """Build a fake ollama.ChatResponse-like object whose .message.content
    returns the given string. ollama's library accepts either attribute or
    dict access; the simplest mockable shape is an object with .message.content.
    """
    resp = MagicMock()
    resp.message.content = content
    return resp


def _make_client(timeout_s=3.0, min_conf=0.5):
    with patch("voice_assistant.nlu.ollama_client.ollama.Client"):
        return OllamaClient(
            host="http://localhost:11434",
            model="qwen2.5:3b-instruct",
            timeout_s=timeout_s,
            temperature=0.1,
            min_confidence=min_conf,
        )


def test_classify_happy_path_returns_intent():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response(
        '{"intent": "open_app", "slots": {"app": "telegram"}, "confidence": 0.9}'
    ))
    intent = client.classify("запусти телегу", "system prompt", _CATALOG)
    assert intent.name == "open_app"
    assert intent.slots == {"app": "telegram"}


def test_classify_passes_messages_and_format_json():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response(
        '{"intent": "minimize_all", "slots": {}, "confidence": 0.9}'
    ))
    client.classify("сверни всё", "my system prompt", _CATALOG)
    args, kwargs = client._client.chat.call_args
    assert kwargs["model"] == "qwen2.5:3b-instruct"
    assert kwargs["format"] == "json"
    msgs = kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "my system prompt"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "сверни всё"
    assert kwargs["options"]["temperature"] == 0.1
    assert kwargs.get("keep_alive") == "5m"


def test_classify_connection_error_marks_unreachable_60s():
    import httpx
    client = _make_client()
    client._client.chat = MagicMock(side_effect=httpx.ConnectError("no route"))
    with patch("voice_assistant.nlu.ollama_client.time.monotonic",
                return_value=1000.0):
        intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"
    # _unreachable_until = mono + 60
    assert client._unreachable_until == pytest.approx(1060.0, abs=0.1)


def test_classify_short_circuits_when_unreachable_cache_active():
    client = _make_client()
    client._client.chat = MagicMock()
    client._unreachable_until = 1e18  # essentially forever
    intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"
    client._client.chat.assert_not_called()


def test_classify_retries_after_unreachable_window_expires():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response(
        '{"intent": "minimize_all", "slots": {}, "confidence": 0.9}'
    ))
    # Set unreachable in the past
    with patch("voice_assistant.nlu.ollama_client.time.monotonic",
                return_value=1000.0):
        client._unreachable_until = 999.0
        intent = client.classify("сверни", "prompt", _CATALOG)
    assert intent.name == "minimize_all"
    client._client.chat.assert_called_once()


def test_classify_model_not_found_marks_permanent_unreachable():
    import ollama
    client = _make_client()
    err = ollama.ResponseError("model 'x' not found", status_code=404)
    client._client.chat = MagicMock(side_effect=err)
    with patch("voice_assistant.nlu.ollama_client.time.monotonic",
                return_value=1000.0):
        intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"
    # Permanent: very large value
    assert client._unreachable_until > 1e8


def test_classify_timeout_returns_unknown_without_caching():
    import httpx
    client = _make_client()
    client._client.chat = MagicMock(side_effect=httpx.ReadTimeout("slow"))
    with patch("voice_assistant.nlu.ollama_client.time.monotonic",
                return_value=1000.0):
        client._unreachable_until = 0
        intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"
    # Timeout is normal — does NOT cache unreachable
    assert client._unreachable_until == 0


def test_classify_generic_exception_returns_unknown():
    client = _make_client()
    client._client.chat = MagicMock(side_effect=RuntimeError("boom"))
    intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"


def test_classify_invalid_json_returns_unknown():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response("not json"))
    intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"


def test_classify_hallucinated_intent_returns_unknown():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response(
        '{"intent": "make_coffee", "slots": {}, "confidence": 0.99}'
    ))
    intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"


def test_warning_logged_once_for_connection_error(caplog):
    import httpx
    client = _make_client()
    client._client.chat = MagicMock(side_effect=httpx.ConnectError("nope"))
    # First call: should mark unreachable, log warning
    client._unreachable_until = 0
    client.classify("hi", "prompt", _CATALOG)
    # Verify the warning flag was set so a second similar call won't re-warn
    assert client._warned_unreachable is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_ollama_client.py -v`
Expected: 11 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `OllamaClient`**

Create `src/voice_assistant/nlu/ollama_client.py`:

```python
from __future__ import annotations
import time
import httpx
import ollama
from loguru import logger

from voice_assistant.core.types import Intent
from voice_assistant.nlu.parse import parse_and_validate


_UNREACHABLE_COOLDOWN_S = 60.0
_PERMANENT_UNREACHABLE_S = 1e12  # effectively forever (decades)
_KEEP_ALIVE = "5m"
_MAX_TOKENS = 100


class OllamaClient:
    """Synchronous classifier that asks a local ollama model to pick an intent.

    Failure policy: any error (connection, timeout, bad JSON, hallucinated
    intent, low confidence) results in Intent.unknown(). Pipeline never blocks
    longer than `timeout_s` and never sees an exception from this layer.
    """

    def __init__(self, host: str, model: str, timeout_s: float,
                 temperature: float, min_confidence: float):
        self._client = ollama.Client(host=host, timeout=timeout_s)
        self._model = model
        self._temperature = temperature
        self._min_confidence = min_confidence
        self._unreachable_until: float = 0.0
        self._warned_unreachable = False
        self._warned_model_missing = False

    def classify(self, text: str, system_prompt: str,
                 catalog: dict[str, dict]) -> Intent:
        if time.monotonic() < self._unreachable_until:
            return Intent.unknown()
        try:
            resp = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                format="json",
                options={"temperature": self._temperature,
                         "num_predict": _MAX_TOKENS},
                keep_alive=_KEEP_ALIVE,
            )
        except (ConnectionError, httpx.ConnectError) as e:
            self._mark_connection_unreachable(e)
            return Intent.unknown()
        except ollama.ResponseError as e:
            status = getattr(e, "status_code", 0)
            msg = str(e).lower()
            if status == 404 or "not found" in msg:
                self._mark_model_missing(e)
            else:
                logger.debug(f"LLM ResponseError {status}: {e}")
            return Intent.unknown()
        except (TimeoutError, httpx.ReadTimeout, httpx.TimeoutException):
            logger.debug(f"LLM timeout on text={text!r}")
            return Intent.unknown()
        except Exception:
            logger.exception("LLM classify unexpected error")
            return Intent.unknown()

        content = resp.message.content if hasattr(resp, "message") \
                  else resp["message"]["content"]
        return parse_and_validate(content, catalog, self._min_confidence)

    def _mark_connection_unreachable(self, exc: Exception) -> None:
        self._unreachable_until = time.monotonic() + _UNREACHABLE_COOLDOWN_S
        if not self._warned_unreachable:
            logger.warning(f"ollama unreachable at {self._client._client.base_url}: "
                            f"{exc}. Suppressing for {int(_UNREACHABLE_COOLDOWN_S)}s.")
            self._warned_unreachable = True

    def _mark_model_missing(self, exc: Exception) -> None:
        self._unreachable_until = time.monotonic() + _PERMANENT_UNREACHABLE_S
        if not self._warned_model_missing:
            logger.error(f"ollama model {self._model!r} not found: {exc}. "
                          f"Run: ollama pull {self._model}")
            self._warned_model_missing = True
```

Notes for the implementer:
- `ollama.ResponseError` constructor: `ollama.ResponseError(error_msg, status_code=...)` — verify with `python -c "import ollama; help(ollama.ResponseError)"`. If `status_code` isn't a kwarg in the installed version, adapt the `_mark_model_missing` branch to detect by message content instead.
- `self._client._client.base_url` reaches into ollama-python's internal httpx client to log the host. If that attribute path is wrong, fall back to a stored host string passed into `__init__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_ollama_client.py -v`
Expected: 11 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 11.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/nlu/ollama_client.py tests/unit/nlu/test_ollama_client.py
git commit -m "feat(nlu): OllamaClient with unreachable cache + graceful degrade"
```

---

## Task 6: `LLMFallbackRouter`

**Files:**
- Create: `src/voice_assistant/nlu/llm_fallback.py`
- Test: `tests/unit/nlu/test_llm_fallback.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/nlu/test_llm_fallback.py
from unittest.mock import MagicMock
from pathlib import Path

from voice_assistant.nlu.llm_fallback import LLMFallbackRouter
from voice_assistant.nlu.base import NLURouter
from voice_assistant.core.types import Transcript, Intent


def _write_commands(tmp_path: Path) -> Path:
    p = tmp_path / "commands.yaml"
    p.write_text(
        '- intent: open_app\n'
        '  examples: ["открой {app}"]\n'
        '  slots: {app: string}\n'
        '- intent: minimize_all\n'
        '  examples: ["сверни всё"]\n'
        '  slots: {}\n', encoding="utf-8")
    return p


def test_primary_known_intent_bypasses_llm(tmp_path):
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent("open_app", {"app": "telegram"}, 1.0)
    client = MagicMock()
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={})
    intent = router.route(Transcript("открой telegram", "ru", 0.9, 100))
    assert intent.name == "open_app"
    client.classify.assert_not_called()


def test_primary_unknown_calls_llm(tmp_path):
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent.unknown()
    client = MagicMock()
    client.classify.return_value = Intent("open_app", {"app": "telegram"}, 0.9)
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={})
    intent = router.route(Transcript("запусти телегу", "ru", 0.9, 100))
    assert intent.name == "open_app"
    client.classify.assert_called_once()
    # Verify it got the transcript text and the prepared system prompt
    args, kwargs = client.classify.call_args
    # Should be either positional or kw; check both shapes
    call_text = kwargs.get("text") or args[0]
    assert call_text == "запусти телегу"


def test_empty_transcript_does_not_call_llm(tmp_path):
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent.unknown()
    client = MagicMock()
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={})
    intent = router.route(Transcript("   ", "ru", 0.9, 100))
    assert intent.name == "unknown"
    client.classify.assert_not_called()


def test_llm_returns_unknown_propagates(tmp_path):
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent.unknown()
    client = MagicMock()
    client.classify.return_value = Intent.unknown()
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={})
    intent = router.route(Transcript("ерунда какая-то", "ru", 0.9, 100))
    assert intent.name == "unknown"


def test_system_prompt_built_at_init(tmp_path):
    """Prompt is assembled once at __init__ and contains catalog intents."""
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent.unknown()
    client = MagicMock()
    client.classify.return_value = Intent.unknown()
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={"телега": "telegram"})
    assert "open_app" in router._system_prompt
    assert "minimize_all" in router._system_prompt
    assert "телега" in router._system_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_llm_fallback.py -v`
Expected: 5 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `LLMFallbackRouter`**

Create `src/voice_assistant/nlu/llm_fallback.py`:

```python
from __future__ import annotations
from pathlib import Path

from voice_assistant.nlu.base import NLURouter
from voice_assistant.nlu.ollama_client import OllamaClient
from voice_assistant.nlu.prompt import load_catalog, build_system_prompt
from voice_assistant.core.types import Transcript, Intent


class LLMFallbackRouter(NLURouter):
    """NLURouter that consults a local LLM when the primary returns unknown.

    Composition pattern: wraps an existing NLURouter (e.g. RulesRouter).
    Rules-known commands skip the LLM entirely; only `unknown` results
    trigger the slow path.
    """

    def __init__(self, primary: NLURouter, client: OllamaClient,
                 commands_path: Path | str,
                 app_aliases: dict[str, str]) -> None:
        self._primary = primary
        self._client = client
        self._catalog = load_catalog(commands_path)
        self._system_prompt = build_system_prompt(self._catalog, app_aliases)

    def route(self, transcript: Transcript) -> Intent:
        primary_intent = self._primary.route(transcript)
        if primary_intent.name != "unknown":
            return primary_intent
        if not transcript.text.strip():
            return primary_intent
        return self._client.classify(
            text=transcript.text,
            system_prompt=self._system_prompt,
            catalog=self._catalog,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_llm_fallback.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 5.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/nlu/llm_fallback.py tests/unit/nlu/test_llm_fallback.py
git commit -m "feat(nlu): LLMFallbackRouter wrapping primary NLU with ollama fallback"
```

---

## Task 7: Wire `LLMFallbackRouter` into `main._build`

**Files:**
- Modify: `src/voice_assistant/main.py`
- Test: extend `tests/unit/test_main.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_main.py`:

```python
def test_build_wraps_nlu_in_llm_fallback_when_enabled(tmp_path, monkeypatch):
    """When cfg.llm.enabled, _build wraps RulesRouter in LLMFallbackRouter."""
    from voice_assistant.nlu.llm_fallback import LLMFallbackRouter
    from voice_assistant.nlu.rules import RulesRouter

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    # Mock OllamaClient so we don't try to connect to a real server
    monkeypatch.setattr("voice_assistant.main.OllamaClient", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: true\n  model: qwen2.5:3b-instruct\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))
    assert isinstance(pipe.nlu, LLMFallbackRouter)
    # And the primary inside is still RulesRouter
    assert isinstance(pipe.nlu._primary, RulesRouter)


def test_build_uses_plain_rules_router_when_llm_disabled(tmp_path, monkeypatch):
    """When cfg.llm.enabled is false, NLU is RulesRouter alone (no wrapping)."""
    from voice_assistant.nlu.rules import RulesRouter
    from voice_assistant.nlu.llm_fallback import LLMFallbackRouter

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))
    assert isinstance(pipe.nlu, RulesRouter)
    assert not isinstance(pipe.nlu, LLMFallbackRouter)
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "llm_fallback or plain_rules"`
Expected: FAIL — `OllamaClient`/`LLMFallbackRouter` not imported in `main`.

- [ ] **Step 3: Edit `main.py`**

In `src/voice_assistant/main.py`:

a) Add imports near the other NLU imports:

```python
from voice_assistant.nlu.llm_fallback import LLMFallbackRouter
from voice_assistant.nlu.ollama_client import OllamaClient
```

b) After the existing `nlu = RulesRouter(...)` line in `_build`, add the wrapping logic:

```python
    nlu = RulesRouter(
        commands_path=str(Path(config_path).parent / "commands.yaml"),
        fuzzy_threshold=cfg.nlu.fuzzy_threshold)
    if cfg.llm.enabled:
        ollama_client = OllamaClient(
            host=cfg.llm.host, model=cfg.llm.model,
            timeout_s=cfg.llm.timeout_s,
            temperature=cfg.llm.temperature,
            min_confidence=cfg.llm.min_confidence)
        nlu = LLMFallbackRouter(
            primary=nlu, client=ollama_client,
            commands_path=Path(config_path).parent / "commands.yaml",
            app_aliases=cfg.app_aliases)
```

The Pipeline construction line `pipe = Pipeline(cfg, asr, nlu, global_registry(), ctx, feedback)` doesn't change — `nlu` is now polymorphic (RulesRouter or LLMFallbackRouter).

- [ ] **Step 4: Run new tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "llm_fallback or plain_rules"`
Expected: 2 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 2.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/main.py tests/unit/test_main.py
git commit -m "feat(main): wrap RulesRouter in LLMFallbackRouter when llm.enabled"
```

---

## Task 8: README + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append LLM Fallback section + manual checklist items to `README.md`**

Open `README.md`. Below the existing "TTS verification checklist" section, append:

```markdown

## LLM Fallback (опционально)

Если правила в `config/commands.yaml` не сматчили команду — спросить локальный LLM:

1. Установи ollama: https://ollama.com/download
2. Запусти сервер: `ollama serve` (в фоне или как сервис)
3. Спулли модель: `ollama pull qwen2.5:3b-instruct` (~2 GB)
4. В `config/default.yaml` поставь `llm.enabled: true`

LLM работает локально (по умолчанию `http://localhost:11434`). Транскрипты не уходят в облако.

Если ollama не запущена или модель не скачана — ассистент работает без LLM-fallback, без ошибок.

## LLM fallback verification checklist

- [ ] `llm.enabled: false` (default): assistant starts identically to before, no ollama dependency
- [ ] `llm.enabled: true` + ollama running + model pulled: rules-known command ("открой блокнот") works as before — no LLM call (verify via DEBUG log silence)
- [ ] LLM-only command ("запусти мне телегу пожалуйста"): resolved to `open_app{app="telegram"}` (assuming alias)
- [ ] LLM-only command, ambiguous ("распакуй файлик"): `Intent.unknown()` → "Не понял, повтори"
- [ ] ollama not running while `llm.enabled: true`: first attempt → WARNING log, subsequent attempts within 60 s → no log spam, all "Не понял, повтори"
- [ ] Model not pulled: ERROR log with hint `ollama pull qwen2.5:3b-instruct`, permanent unreachable for that process
- [ ] LLM-resolved destructive intent ("выключи нахрен" → `shutdown`): triggers existing confirmation flow — destructive intents NOT bypassed
```

- [ ] **Step 2: Run full test suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Coverage report optional but recommended.

- [ ] **Step 3: Coverage check**

Run: `.\.venv\Scripts\python.exe -m pytest --cov=voice_assistant --cov-report=term-missing -q`
Expected: new modules at ≥80%:
- `nlu/prompt.py` — should approach 100% (pure data)
- `nlu/parse.py` — should be 100% (14 tests cover every branch)
- `nlu/ollama_client.py` — likely 85-95% (some defensive `except Exception` paths)
- `nlu/llm_fallback.py` — should approach 100%
- `config.py` — small delta, still ≥95%

Note in commit message any module below 80% with what's uncovered.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: LLM fallback setup notes + manual checklist"
```

---

## Self-Review Notes

- **Spec coverage:** LLMConfig (T1), prompt builder + catalog loader (T2), parse_and_validate (T3), deps + yaml (T4), OllamaClient with full failure matrix + unreachable cache (T5), LLMFallbackRouter wrapping primary (T6), main wiring + config gate (T7), README + checklist (T8). All failure modes from spec §7 are covered by Tasks 3 (parser-side) and 5 (client-side).

- **Task ordering caveats:**
  - Task 4 (install ollama) must run before Task 5 — module-level `import ollama` would otherwise break test collection.
  - Task 3 (`parse.py`) must run before Task 5 — `OllamaClient` imports `parse_and_validate`.
  - Task 6 imports from Task 2 (`prompt.py`) and Task 5 (`OllamaClient`).
  - Task 7 imports from Task 6.

- **Type consistency:** `parse_and_validate(content, catalog, min_confidence)` signature used in T3 matches the call in T5's OllamaClient. `OllamaClient(host, model, timeout_s, temperature, min_confidence)` constructor used in T5 matches the call in T7's `main._build`. `LLMFallbackRouter(primary, client, commands_path, app_aliases)` matches the call in T7. Pipeline's `nlu: NLURouter` parameter (untouched) accepts both `RulesRouter` and `LLMFallbackRouter` since both subclass `NLURouter`.

- **API verification before Task 5:** the smoke check in Task 4 step 3 surfaces ollama API version + chat signature so Task 5 implementer can adapt if the signature shifted (e.g., `format` kwarg renamed). If `ollama.ResponseError(error_msg, status_code=...)` constructor differs in the installed version, the test stub in Task 5 must adapt.

- **Out of scope (per spec §12):** transcript privacy gate, response caching, per-intent allowlist, streaming output, custom fine-tune, multi-turn memory. If the implementer is tempted, STOP and report.

- **Test density:** ~40 new tests across 6 test files. Expected total after Task 8: ~145 (current 105 + 40).

- **No model is downloaded by these tests.** All ollama calls are mocked. The integration test (`@pytest.mark.requires_ollama`) is mentioned in the spec but NOT included in this plan — it's optional and lives outside the default suite.
