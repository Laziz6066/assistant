# Multi-turn Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-turn slot inheritance via pronoun resolution — "закрой его" right after "открой telegram" resolves to `close_app(app="telegram")`. Pure rules-based, no LLM dependency, no new packages.

**Architecture:** `ContextStore` (deque + TTL + Lock) holds recent intents. `ContextualRouter(NLURouter)` wraps the inner router and rewrites pronouns to the most recent entity before delegating. `Pipeline.process_segment` writes successful intents into the store. Default-on; falls through cleanly when context is empty or expired.

**Tech Stack:** Python 3.11+, stdlib only (`re`, `collections.deque`, `threading`, `time`).

**Depends on:** voice-assistant branch at commit `18b0535` (multi-turn design spec) or later. Spec: `docs/superpowers/specs/2026-05-20-multi-turn-dialog-design.md`.

---

## File Structure

**New files:**
- `src/voice_assistant/nlu/context_store.py` — `ContextStore` (deque + Lock + TTL)
- `src/voice_assistant/nlu/contextual.py` — `ContextualRouter(NLURouter)` wrapping inner router
- `tests/unit/nlu/test_context_store.py`
- `tests/unit/nlu/test_contextual.py`
- `tests/integration/test_dialog.py` — two-turn end-to-end

**Modified files:**
- `src/voice_assistant/config.py` — add `DialogConfig` + `AppConfig.dialog`
- `src/voice_assistant/main.py` — `Pipeline.__init__` gains `context_store`; `process_segment` writes after success; `_build` constructs store + wraps NLU
- `config/default.yaml` — add `dialog` section
- `README.md` — Dialog section + manual checklist
- `tests/unit/test_main.py` — extend with dialog wiring tests
- `tests/unit/test_config.py` — extend with `DialogConfig` tests

No `pyproject.toml` change — no new dependencies.

---

## Task 1: `DialogConfig` in `config.py`

**Files:**
- Modify: `src/voice_assistant/config.py`
- Test: extend `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py`:

```python
from voice_assistant.config import DialogConfig


def test_dialog_config_default_values():
    cfg = DialogConfig()
    assert cfg.enabled is True
    assert cfg.context_ttl_s == 60.0
    assert cfg.context_size == 5


def test_dialog_config_accepts_overrides():
    cfg = DialogConfig(enabled=False, context_ttl_s=30.0, context_size=10)
    assert cfg.enabled is False
    assert cfg.context_ttl_s == 30.0
    assert cfg.context_size == 10


def test_app_config_has_dialog_section_default_enabled():
    cfg = AppConfig()
    assert cfg.dialog.enabled is True
    assert cfg.dialog.context_ttl_s == 60.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v -k dialog`
Expected: 3 FAILs with `ImportError: cannot import name 'DialogConfig'`.

- [ ] **Step 3: Add `DialogConfig` and wire into `AppConfig`**

Edit `src/voice_assistant/config.py`. After the existing `TrayConfig` class and before `AppConfig`, insert:

```python
class DialogConfig(BaseModel):
    enabled: bool = True
    context_ttl_s: float = 60.0
    context_size: int = 5
```

Inside `AppConfig`, add the `dialog` field after `tray`:

```python
dialog: DialogConfig = Field(default_factory=DialogConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v -k dialog`
Expected: 3 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 3 = 208.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/config.py tests/unit/test_config.py
git commit -m "feat(config): add DialogConfig for multi-turn dialog"
```

---

## Task 2: `ContextStore`

**Files:**
- Create: `src/voice_assistant/nlu/context_store.py`
- Test: `tests/unit/nlu/test_context_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/nlu/test_context_store.py
from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.core.types import Intent


def _intent(name="open_app", slots=None, confidence=1.0):
    return Intent(name=name, slots=slots or {"app": "telegram"},
                  confidence=confidence)


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start
    def __call__(self):
        return self.now


def test_add_stores_eligible_intent():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(_intent())
    entity = store.get_recent_entity()
    assert entity == ("telegram", "app")


def test_add_skips_unknown():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent.unknown())
    assert store.get_recent_entity() is None


def test_add_skips_confirm_yes():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="confirm_yes", slots={}, confidence=1.0))
    assert store.get_recent_entity() is None


def test_add_skips_slotless():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="minimize_all", slots={}, confidence=1.0))
    assert store.get_recent_entity() is None


def test_get_recent_entity_returns_newest():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(_intent(slots={"app": "telegram"}))
    store.add(_intent(slots={"app": "chrome"}))
    entity = store.get_recent_entity()
    assert entity == ("chrome", "app")


def test_get_recent_entity_returns_none_when_empty():
    store = ContextStore(max_size=5, ttl_s=60.0)
    assert store.get_recent_entity() is None


def test_get_recent_entity_respects_ttl():
    clock = _FakeClock(start=1000.0)
    store = ContextStore(max_size=5, ttl_s=60.0, clock=clock)
    store.add(_intent(slots={"app": "telegram"}))
    # Advance past TTL
    clock.now = 1100.0
    assert store.get_recent_entity() is None


def test_get_recent_entity_respects_slot_priority():
    store = ContextStore(max_size=5, ttl_s=60.0)
    # Intent with both app and name — app wins
    store.add(Intent(name="X", slots={"name": "n1", "app": "a1"},
                     confidence=1.0))
    entity = store.get_recent_entity()
    assert entity == ("a1", "app")


def test_get_recent_entity_prefers_name_when_no_app():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="open_path", slots={"name": "downloads"},
                     confidence=1.0))
    entity = store.get_recent_entity()
    assert entity == ("downloads", "name")


def test_get_recent_entity_prefers_query_over_url():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="web_search",
                     slots={"url": "x.com", "query": "weather"},
                     confidence=1.0))
    entity = store.get_recent_entity()
    assert entity == ("weather", "query")


def test_deque_evicts_oldest_at_max_size():
    store = ContextStore(max_size=2, ttl_s=60.0)
    store.add(_intent(slots={"app": "one"}))
    store.add(_intent(slots={"app": "two"}))
    store.add(_intent(slots={"app": "three"}))
    # max_size=2 → "one" evicted, "three" is newest
    entity = store.get_recent_entity()
    assert entity == ("three", "app")


def test_clear_empties_store():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(_intent())
    store.clear()
    assert store.get_recent_entity() is None


def test_skip_intent_with_non_string_slot():
    """volume_set has level=int — not a usable entity for pronoun resolution."""
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="volume_set", slots={"level": 50}, confidence=1.0))
    # No string slot in priority order → no entity
    assert store.get_recent_entity() is None


def test_skip_intent_with_empty_string_slot():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="open_app", slots={"app": "   "}, confidence=1.0))
    assert store.get_recent_entity() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_context_store.py -v`
Expected: 14 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `ContextStore`**

Create `src/voice_assistant/nlu/context_store.py`:

```python
from __future__ import annotations
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Deque

from voice_assistant.core.types import Intent


_ENTITY_SLOT_PRIORITY: tuple[str, ...] = ("app", "name", "query", "url")
_SKIP_INTENTS: frozenset[str] = frozenset({"unknown", "confirm_yes"})


class ContextStore:
    """Bounded LRU of recently dispatched intents with TTL expiration.

    Thread-safe: a single Lock guards all mutations and reads.

    Only stores intents that:
      - have at least one string slot in _ENTITY_SLOT_PRIORITY
      - are not "unknown" or "confirm_yes"
    """

    def __init__(self, max_size: int = 5, ttl_s: float = 60.0,
                 clock: Callable[[], float] | None = None) -> None:
        self._buf: Deque[tuple[Intent, float]] = deque(maxlen=max_size)
        self._ttl_s = ttl_s
        self._clock = clock if clock is not None else time.monotonic
        self._lock = threading.Lock()

    def add(self, intent: Intent) -> None:
        if intent.name in _SKIP_INTENTS:
            return
        if not self._has_usable_entity(intent):
            return
        with self._lock:
            self._buf.append((intent, self._clock()))

    def get_recent_entity(self) -> tuple[str, str] | None:
        now = self._clock()
        with self._lock:
            for intent, ts in reversed(self._buf):  # newest first
                if now - ts > self._ttl_s:
                    return None  # newer-first iteration; if this expired,
                                  # everything older is also expired
                for slot_name in _ENTITY_SLOT_PRIORITY:
                    val = intent.slots.get(slot_name)
                    if isinstance(val, str) and val.strip():
                        return (val.strip(), slot_name)
        return None

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    @staticmethod
    def _has_usable_entity(intent: Intent) -> bool:
        for slot_name in _ENTITY_SLOT_PRIORITY:
            val = intent.slots.get(slot_name)
            if isinstance(val, str) and val.strip():
                return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_context_store.py -v`
Expected: 14 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 14 = 222.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/nlu/context_store.py tests/unit/nlu/test_context_store.py
git commit -m "feat(nlu): ContextStore with TTL + LRU + slot priority"
```

---

## Task 3: `ContextualRouter`

**Files:**
- Create: `src/voice_assistant/nlu/contextual.py`
- Test: `tests/unit/nlu/test_contextual.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/nlu/test_contextual.py
from unittest.mock import MagicMock
import pytest

from voice_assistant.nlu.contextual import ContextualRouter
from voice_assistant.nlu.base import NLURouter
from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.core.types import Transcript, Intent


def _t(text):
    return Transcript(text=text, language="ru", confidence=0.9,
                       duration_ms=500)


def _mock_inner(return_intent):
    inner = MagicMock(spec=NLURouter)
    inner.route.return_value = return_intent
    return inner


def test_passthrough_when_no_pronouns():
    inner = _mock_inner(Intent("open_app", {"app": "x"}, 1.0))
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("открой блокнот"))
    args, _ = inner.route.call_args
    assert args[0].text == "открой блокнот"


def test_passthrough_when_store_empty():
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("закрой его"))
    args, _ = inner.route.call_args
    assert args[0].text == "закрой его"


def test_passthrough_when_store_none():
    inner = _mock_inner(Intent.unknown())
    router = ContextualRouter(inner=inner, store=None)
    router.route(_t("закрой его"))
    args, _ = inner.route.call_args
    assert args[0].text == "закрой его"


def test_rewrite_replaces_simple_pronoun():
    inner = _mock_inner(Intent("close_app", {"app": "telegram"}, 1.0))
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("закрой его"))
    args, _ = inner.route.call_args
    assert args[0].text == "закрой telegram"


def test_rewrite_replaces_multiple_pronouns_with_same_entity():
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "chrome"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("открой его и сверни это"))
    args, _ = inner.route.call_args
    assert args[0].text == "открой chrome и сверни chrome"


@pytest.mark.parametrize("pronoun", [
    "его", "её", "ее", "их",
    "это", "этот", "эту", "этого", "этому",
    "тот", "та", "то", "того", "тому", "ту",
])
def test_each_russian_pronoun_recognized(pronoun):
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "X"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t(f"закрой {pronoun}"))
    args, _ = inner.route.call_args
    assert "X" in args[0].text


@pytest.mark.parametrize("pronoun", ["it", "this", "that"])
def test_each_english_pronoun_recognized(pronoun):
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "X"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t(f"close {pronoun}"))
    args, _ = inner.route.call_args
    assert "X" in args[0].text


def test_case_insensitive_match():
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("Закрой ЕГО"))
    args, _ = inner.route.call_args
    # Case in rewritten output isn't preserved exactly — pronoun replaced
    # with entity value verbatim. We just verify the entity is present.
    assert "telegram" in args[0].text.lower()


def test_word_boundary_prevents_partial_match():
    """The pronoun 'это' must not match inside 'этузиазм'."""
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("этузиазм"))
    args, _ = inner.route.call_args
    assert args[0].text == "этузиазм"


def test_expired_context_treated_as_empty():
    inner = _mock_inner(Intent.unknown())
    clock = {"now": 1000.0}
    store = ContextStore(max_size=5, ttl_s=60.0, clock=lambda: clock["now"])
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    clock["now"] = 1100.0  # past TTL
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("закрой его"))
    args, _ = inner.route.call_args
    # Pronoun not replaced — entity expired
    assert args[0].text == "закрой его"


def test_inner_router_exception_propagates():
    inner = MagicMock(spec=NLURouter)
    inner.route.side_effect = RuntimeError("boom")
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "X"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    with pytest.raises(RuntimeError, match="boom"):
        router.route(_t("закрой его"))


def test_rewritten_transcript_preserves_metadata():
    """The Transcript object passed to inner.route should have the same
    language/confidence/duration_ms as the original, only text changed."""
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "X"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    original = Transcript(text="закрой его", language="ru",
                           confidence=0.87, duration_ms=421)
    router.route(original)
    args, _ = inner.route.call_args
    inner_t = args[0]
    assert inner_t.language == "ru"
    assert inner_t.confidence == 0.87
    assert inner_t.duration_ms == 421
    assert "X" in inner_t.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_contextual.py -v`
Expected: many FAILs with `ModuleNotFoundError`. (Parametrized tests will show 15 + 3 = 18 plus the others; total ~30 FAILs counting parametrize variants.)

- [ ] **Step 3: Implement `ContextualRouter`**

Create `src/voice_assistant/nlu/contextual.py`:

```python
from __future__ import annotations
import re
from dataclasses import replace

from loguru import logger

from voice_assistant.nlu.base import NLURouter
from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.core.types import Transcript, Intent


_PRONOUNS: tuple[str, ...] = (
    "его", "её", "ее", "их",
    "это", "этот", "эту", "этого", "этому",
    "тот", "та", "то", "того", "тому", "ту",
    "it", "this", "that",
)

_PRONOUN_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in _PRONOUNS) + r")\b",
    flags=re.IGNORECASE,
)


class ContextualRouter(NLURouter):
    """NLURouter that rewrites pronouns to the most recent entity from
    `ContextStore` before delegating to an inner router.

    If `store` is None, or the store has no eligible context, the original
    transcript is passed through unchanged.
    """

    def __init__(self, inner: NLURouter,
                 store: ContextStore | None) -> None:
        self._inner = inner
        self._store = store

    def route(self, transcript: Transcript) -> Intent:
        rewritten = self._rewrite(transcript.text)
        if rewritten == transcript.text:
            return self._inner.route(transcript)
        logger.debug(f"context rewrite: {transcript.text!r} → {rewritten!r}")
        return self._inner.route(replace(transcript, text=rewritten))

    def _rewrite(self, text: str) -> str:
        if self._store is None:
            return text
        if not _PRONOUN_RE.search(text):
            return text
        entity = self._store.get_recent_entity()
        if entity is None:
            return text
        value, _slot = entity
        return _PRONOUN_RE.sub(value, text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/nlu/test_contextual.py -v`
Expected: all PASS. With parametrize expansion: 15 Russian + 3 English pronoun tests + 9 other = 27 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = 222 + 27 = 249.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/nlu/contextual.py tests/unit/nlu/test_contextual.py
git commit -m "feat(nlu): ContextualRouter — pronoun-based slot inheritance"
```

---

## Task 4: Add `dialog` section to `config/default.yaml`

**Files:**
- Modify: `config/default.yaml`

- [ ] **Step 1: Append `dialog` section to `config/default.yaml`**

Append:

```yaml
dialog:
  enabled: true
  context_ttl_s: 60.0
  context_size: 5
```

- [ ] **Step 2: Smoke check**

```bash
.\.venv\Scripts\python.exe -c "from voice_assistant.config import load_config; c = load_config('config/default.yaml'); print(c.dialog)"
```
Expected: `enabled=True context_ttl_s=60.0 context_size=5`.

- [ ] **Step 3: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green (no new tests).

- [ ] **Step 4: Commit**

```bash
git add config/default.yaml
git commit -m "chore: add dialog section to default.yaml"
```

---

## Task 5: Plumb `context_store` through `Pipeline`

Add the optional `context_store` parameter to `Pipeline.__init__` and write successful intents to it.

**Files:**
- Modify: `src/voice_assistant/main.py`
- Test: extend `tests/unit/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_main.py`:

```python
def test_pipeline_constructor_accepts_context_store():
    """Pipeline.__init__ must accept context_store kwarg (default None)."""
    from voice_assistant.main import Pipeline
    from voice_assistant.nlu.context_store import ContextStore
    store = ContextStore()
    pipe = Pipeline(
        config=AppConfig(), asr=MagicMock(), nlu=MagicMock(),
        registry=MagicMock(), ctx=MagicMock(), feedback=MagicMock(),
        context_store=store,
    )
    assert pipe.context_store is store


def test_pipeline_writes_successful_intent_to_context_store():
    """Successful dispatch → context_store.add(intent) is called."""
    from voice_assistant.main import Pipeline
    from voice_assistant.core.types import (
        AudioSegment, Transcript, Intent, ExecutionResult,
    )
    import numpy as np

    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой telegram", "ru", 0.9, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "telegram"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult(
        success=True, message="ok", tts_response="Открыл")
    feedback = MagicMock()
    store = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                     ctx=MagicMock(), feedback=feedback, context_store=store)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    store.add.assert_called_once()
    added_intent = store.add.call_args.args[0]
    assert added_intent.name == "open_app"
    assert added_intent.slots == {"app": "telegram"}


def test_pipeline_does_not_write_failed_dispatch_to_store():
    """When dispatch returns success=False, the store is NOT updated."""
    from voice_assistant.main import Pipeline
    from voice_assistant.core.types import (
        AudioSegment, Transcript, Intent, ExecutionResult,
    )
    import numpy as np

    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой xyz", "ru", 0.9, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "xyz"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult.fail("not found")
    feedback = MagicMock()
    store = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                     ctx=MagicMock(), feedback=feedback, context_store=store)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    store.add.assert_not_called()


def test_pipeline_without_context_store_does_not_raise():
    """context_store=None is a valid configuration."""
    from voice_assistant.main import Pipeline
    from voice_assistant.core.types import (
        AudioSegment, Transcript, Intent, ExecutionResult,
    )
    import numpy as np

    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой telegram", "ru", 0.9, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "telegram"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult.ok("ok",
                                                         tts_response="Открыл")
    feedback = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                     ctx=MagicMock(), feedback=feedback)  # context_store omitted
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    # No exception means PASS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "context_store"`
Expected: 4 FAILs — `Pipeline.__init__` doesn't accept `context_store` yet.

- [ ] **Step 3: Edit `main.py`**

a) Add the import at the top with the other NLU imports:

```python
from voice_assistant.nlu.context_store import ContextStore
```

b) Find the `Pipeline.__init__` signature:

```python
class Pipeline:
    def __init__(self, config: AppConfig, asr: ASREngine, nlu: NLURouter,
                 registry: Registry, ctx: ExecutorContext,
                 feedback: FeedbackSink):
```

Replace with:

```python
class Pipeline:
    def __init__(self, config: AppConfig, asr: ASREngine, nlu: NLURouter,
                 registry: Registry, ctx: ExecutorContext,
                 feedback: FeedbackSink,
                 context_store: ContextStore | None = None):
```

c) After the existing assignments in `__init__` (after `self.feedback = feedback`), add:

```python
        self.context_store = context_store
```

d) Find the `process_segment` body where dispatch happens:

```python
        result = self.registry.dispatch(intent, self.ctx)
        logger.info(f"intent={intent.name} success={result.success}")
        self.feedback.emit(result.tts_response, success=result.success)
```

Replace with:

```python
        result = self.registry.dispatch(intent, self.ctx)
        logger.info(f"intent={intent.name} success={result.success}")
        if result.success and self.context_store is not None:
            self.context_store.add(intent)
        self.feedback.emit(result.tts_response, success=result.success)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "context_store"`
Expected: 4 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 4 = 253.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/main.py tests/unit/test_main.py
git commit -m "feat(main): Pipeline accepts context_store, writes on success"
```

---

## Task 6: Wire `ContextStore` + `ContextualRouter` into `_build`

**Files:**
- Modify: `src/voice_assistant/main.py`
- Test: extend `tests/unit/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_main.py`:

```python
def test_build_wraps_in_contextual_router_when_dialog_enabled(tmp_path,
                                                                monkeypatch):
    from voice_assistant.nlu.contextual import ContextualRouter
    from voice_assistant.nlu.context_store import ContextStore

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    monkeypatch.setattr("voice_assistant.main.SystemTray", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n"
        "tray:\n  enabled: false\n"
        "dialog:\n  enabled: true\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback, tray = _build(
        str(tmp_path / "default.yaml"))
    assert isinstance(pipe.nlu, ContextualRouter)
    assert isinstance(pipe.context_store, ContextStore)


def test_build_skips_contextual_router_when_dialog_disabled(tmp_path,
                                                              monkeypatch):
    from voice_assistant.nlu.contextual import ContextualRouter

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    monkeypatch.setattr("voice_assistant.main.SystemTray", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n"
        "tray:\n  enabled: false\n"
        "dialog:\n  enabled: false\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback, tray = _build(
        str(tmp_path / "default.yaml"))
    assert not isinstance(pipe.nlu, ContextualRouter)
    assert pipe.context_store is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "contextual_router"`
Expected: FAILs — `_build` doesn't construct `ContextStore` or wrap NLU in `ContextualRouter` yet.

- [ ] **Step 3: Edit `main.py`**

a) Add the import near other NLU imports:

```python
from voice_assistant.nlu.contextual import ContextualRouter
```

b) Find the NLU construction in `_build`. After the existing chain (RulesRouter, optional LLMFallbackRouter wrap), and BEFORE the Pipeline constructor call. Currently it looks roughly like:

```python
    nlu = RulesRouter(
        commands_path=str(Path(config_path).parent / "commands.yaml"),
        fuzzy_threshold=cfg.nlu.fuzzy_threshold)
    if cfg.llm.enabled:
        ollama_client = OllamaClient(...)
        nlu = LLMFallbackRouter(...)
    # ... feedback construction ...
    pipe = Pipeline(cfg, asr, nlu, global_registry(), ctx, feedback)
```

After all the NLU wrapping (i.e., immediately before `pipe = Pipeline(...)`), insert:

```python
    context_store: ContextStore | None = None
    if cfg.dialog.enabled:
        context_store = ContextStore(
            max_size=cfg.dialog.context_size,
            ttl_s=cfg.dialog.context_ttl_s,
        )
        nlu = ContextualRouter(inner=nlu, store=context_store)
```

c) Update the Pipeline construction to pass `context_store`:

```python
    pipe = Pipeline(cfg, asr, nlu, global_registry(), ctx, feedback,
                     context_store=context_store)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "contextual_router"`
Expected: 2 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 2 = 255. **Watch for regressions** in pre-existing `_build` tests — they unpack 7-tuple, and most of them use `dialog.enabled: true` by default (since they don't set it explicitly, and the default is now `true`). That means `pipe.nlu` is now a `ContextualRouter`, not `RulesRouter`. If any test asserts `isinstance(pipe.nlu, RulesRouter)`, it must either (a) set `dialog.enabled: false` in the YAML, or (b) drill into `pipe.nlu._inner` to find the RulesRouter.

Look specifically at:
- `test_build_uses_plain_rules_router_when_llm_disabled` (LLM task) — this one asserts `isinstance(pipe.nlu, RulesRouter)`. Add `dialog:\n  enabled: false\n` to its YAML, OR update the assertion to `isinstance(pipe.nlu._inner if isinstance(pipe.nlu, ContextualRouter) else pipe.nlu, RulesRouter)`. Simpler: set dialog.enabled=false in that test's YAML.
- `test_build_wraps_nlu_in_llm_fallback_when_enabled` (LLM task) — asserts `isinstance(pipe.nlu, LLMFallbackRouter)`. Same issue. Set dialog.enabled=false.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/main.py tests/unit/test_main.py
git commit -m "feat(main): wire ContextStore + ContextualRouter into _build"
```

---

## Task 7: Integration test

**Files:**
- Create: `tests/integration/test_dialog.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_dialog.py
"""End-to-end multi-turn dialog test.

Uses real RulesRouter, ContextStore, ContextualRouter; mocks ASR and
platform_ops. Verifies that 'закрой его' after 'открой телега' is
resolved to close_app{app=telegram} via the app_aliases mapping.
"""
import numpy as np
from unittest.mock import MagicMock

from voice_assistant.config import AppConfig
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.nlu.contextual import ContextualRouter
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.executor.plugins import apps as apps_plugin
from voice_assistant.core.types import AudioSegment, Transcript
from voice_assistant.main import Pipeline


def test_two_turn_open_then_close(tmp_path):
    cmds = tmp_path / "commands.yaml"
    cmds.write_text(
        '- intent: open_app\n'
        '  examples: ["открой {app}", "запусти {app}"]\n'
        '  slots: {app: string}\n'
        '- intent: close_app\n'
        '  examples: ["закрой {app}"]\n'
        '  slots: {app: string}\n',
        encoding="utf-8")

    cfg = AppConfig(app_aliases={"телега": "telegram"})
    asr = MagicMock()
    store = ContextStore(max_size=5, ttl_s=60.0)
    inner_nlu = RulesRouter(commands_path=cmds, fuzzy_threshold=85)
    nlu = ContextualRouter(inner=inner_nlu, store=store)
    reg = Registry()
    apps_plugin.register(reg)
    ops = MagicMock()
    ctx = ExecutorContext(config=cfg, platform_ops=ops)
    feedback = MagicMock()

    pipe = Pipeline(cfg, asr, nlu, reg, ctx, feedback,
                     context_store=store)

    # Turn 1: "открой телега" — opens telegram, store records intent
    asr.transcribe.return_value = Transcript("открой телега", "ru", 0.9, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    ops.launch_app.assert_called_once_with("telegram")

    # Turn 2: "закрой его" — should resolve to close_app(app=telegram)
    asr.transcribe.return_value = Transcript("закрой его", "ru", 0.9, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    # close_app via apps_plugin → platform_ops.close_app("telegram")
    ops.close_app.assert_called_once_with("telegram")
```

- [ ] **Step 2: Run the integration test**

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_dialog.py -v`
Expected: PASS.

If `ops.close_app` is not called with "telegram", investigate:
- Did `store.add` get the right intent after turn 1? (Add `print(store.get_recent_entity())` between turns.)
- Did `ContextualRouter._rewrite` produce "закрой telegram"? (Add `logger.debug` is already there — set log level to DEBUG.)
- Does the `close_app` rule match "закрой telegram"? Verify with `RulesRouter(...).route(Transcript("закрой telegram", "ru", 1.0, 100))`.

- [ ] **Step 3: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 1 = 256.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_dialog.py
git commit -m "test: integration test for multi-turn dialog (open then close)"
```

---

## Task 8: README + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append Dialog section + manual checklist**

Below the existing "System-tray verification checklist", append:

```markdown

## Multi-turn dialog (slot inheritance)

После выполнения команды с слотом ассистент короткое время (60 с по умолчанию) помнит её аргумент и понимает местоимения:

```
открой telegram     → запускает Telegram
закрой его          → закрывает Telegram (наследуется app=telegram)
```

Работает для русских и английских местоимений: `его, её, их, это, этот, эту, того, тому, ту, it, this, that`. Состояние очищается через `dialog.context_ttl_s` секунд.

Отключить: `dialog.enabled: false` в `config/default.yaml`. Контекст хранится только в памяти — после рестарта пустой.

## Multi-turn dialog verification checklist

- [ ] "открой блокнот" → "закрой его" → блокнот закрывается
- [ ] Пауза 70 секунд между turns → второй turn даёт "Не понял, повтори"
- [ ] "сверни всё" (slotless) → "закрой его" → "Не понял" (нет entity)
- [ ] `dialog.enabled: false` → "открой блокнот" → "закрой его" → "Не понял"
- [ ] "открой telegram" → "открой это" → пытается открыть telegram повторно
- [ ] Цепочка: `open_app(telegram)` → `open_app(chrome)` → "закрой его" → закрывает Chrome (последняя entity)
- [ ] `confirm_yes` после команды НЕ затирает context: "выключи компьютер" → "да" → "верни его" не наследует "yes"
```

- [ ] **Step 2: Run full test suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green at 256.

- [ ] **Step 3: Coverage check**

Run: `.\.venv\Scripts\python.exe -m pytest --cov=voice_assistant --cov-report=term-missing -q`
Expected: new modules at ≥80%:
- `nlu/context_store.py` — should approach 100%
- `nlu/contextual.py` — should approach 100%
- `config.py` — still ≥92%

Note any module below 80% in your commit message.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: multi-turn dialog setup notes + manual checklist"
```

---

## Self-Review Notes

- **Spec coverage:**
  - `DialogConfig` (T1)
  - `ContextStore` with TTL + LRU + skip filters + slot priority (T2)
  - `ContextualRouter` with pronoun regex + rewrite (T3)
  - `dialog` yaml section (T4)
  - `Pipeline.context_store` + write-on-success (T5)
  - `_build` wires `ContextStore` + `ContextualRouter` (T6)
  - End-to-end integration test (T7)
  - README + manual checklist (T8)
  - All spec §7 error rows: skip-filters tested (T2), TTL expiry tested (T2, T3), `store=None` tested (T3), inner-exception propagation tested (T3), `context_store=None` tested (T5).

- **Task ordering:**
  - T2 (`ContextStore`) before T3 (`ContextualRouter` imports it).
  - T5 (Pipeline plumbing) before T6 (`_build` constructs the store and passes to Pipeline).
  - T6 must update pre-existing tests that asserted `isinstance(pipe.nlu, RulesRouter)` or `isinstance(pipe.nlu, LLMFallbackRouter)` — fix listed in T6 Step 5.
  - T7 depends on T5 + T6 wiring.

- **Type consistency:**
  - `ContextStore(max_size, ttl_s, clock=None)` constructor used in T2 matches the call sites in T5/T6.
  - `ContextualRouter(inner, store)` matches the call in T6.
  - `Pipeline(..., context_store=None)` matches T5 + T6.
  - `Intent.slots[str]` is `int | str` per `core/types.py`; `ContextStore._has_usable_entity` checks `isinstance(val, str)` which correctly skips int slots (`volume_set.level`).

- **Spec deviations:** none planned. `Intent` is imported but not used in `contextual.py` — remove the import there to avoid dead imports.

  *Actually wait — let me check.* `contextual.py` does `from voice_assistant.core.types import Transcript, Intent`. `Intent` is only referenced in the return type annotation via `NLURouter.route -> Intent`. Since we use `from __future__ import annotations`, the annotation is a string at runtime and the import is unused. **Either remove `Intent` from the import OR add `# noqa: F401`.** Plan defers this nit to implementer judgment.

- **Out of scope** (per spec §11): LLM-enriched dialog, verb-aware rewriting, cross-session memory, multiple-entity disambiguation, inverse operations.

- **Test density:** ~30 new tests (3 config + 14 ContextStore + 18 ContextualRouter via parametrize + 6 Pipeline/build + 1 integration). Expected total after T8: ~256 (current 205 + 51 — adjust if parametrize count differs).
