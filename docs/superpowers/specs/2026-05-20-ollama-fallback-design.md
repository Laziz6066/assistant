# ollama LLM Fallback — Design Spec

**Date:** 2026-05-20
**Status:** Approved, ready for implementation plan
**Sub-project:** Beta (post-MVP, post-Piper-TTS)
**Depends on:** voice-assistant MVP + Piper TTS at commit `5a0a8bf` or later on branch `worktree-voice-assistant-mvp`

## 1. Goal

When `RulesRouter` cannot match a user utterance to any rule in `commands.yaml`, ask a local LLM (via ollama) to classify the utterance into a known intent. This catches phrasings the rules don't cover (e.g. *"запусти мне телегу пожалуйста"* → `open_app{app="telegram"}`) without sacrificing the latency and determinism of the rules path for known commands.

## 2. Scope

**In:**
- New `LLMFallbackRouter(NLURouter)` that wraps a primary `NLURouter` and queries ollama when the primary returns `unknown`
- New `OllamaClient` that calls ollama's chat API with `format="json"`, validates the response, and returns an `Intent`
- Prompt construction from the live `commands.yaml` intent catalogue
- Validation: catalog membership, confidence threshold, slot type coercion, unreachability cache
- Configuration via `LLMConfig`
- `enabled: false` by default (requires ollama + model pull)

**Out (deferred):**
- Few-shot examples drawn from session history
- Chain-of-thought reasoning prompts
- Streaming output / partial-intent emission
- Model warm-up on startup
- Retry / exponential backoff on transient failures
- Auto-pull of model on first run
- LLM-driven chat mode (open-ended responses)
- LLM-side memory of prior turns (multi-turn dialog) — separate Beta feature
- Per-intent LLM whitelist (destructive intents already protected by confirm flow)

## 3. Decisions

| Question | Decision |
|---|---|
| LLM output format | JSON: `{intent, slots, confidence}`, ollama's `format="json"` mode |
| Default model | `qwen2.5:3b-instruct` (~2 GB, strong Russian, fast structured output) |
| Latency budget | 3 s sync timeout; on timeout return `Intent.unknown()` |
| Integration point | `LLMFallbackRouter` wraps `RulesRouter`; Pipeline unchanged |
| Failure policy | Graceful degrade — any failure → `Intent.unknown()` → user gets "Не понял, повтори" |
| Unreachability cache | 60 s cache when connection fails; permanent cache on model 404 (until restart) |
| Default `enabled` | `false` (user opts in after installing ollama + pulling model) |
| Min confidence threshold | `0.5` (below → `Intent.unknown()`) |
| Destructive intents | Allowed — existing confirm-flow (`shutdown`/`reboot` → "да" within 5 s) is the safety net |
| Privacy | All-local (ollama on `localhost`). Transcript text → LLM is acceptable since `store_transcripts: false` doesn't gate this — but the same gate could be added in a future iteration |

## 4. Architecture

### 4.1 New files

```
src/voice_assistant/nlu/
  llm_fallback.py    # LLMFallbackRouter(NLURouter) — wraps primary router
  ollama_client.py   # OllamaClient — HTTP call + JSON parse + validation
  prompt.py          # build_system_prompt() — assembles prompt from catalog
```

### 4.2 Modified files

```
src/voice_assistant/config.py
  + class LLMConfig(BaseModel):
      enabled: bool = False
      model: str = "qwen2.5:3b-instruct"
      host: str = "http://localhost:11434"
      timeout_s: float = 3.0
      temperature: float = 0.1
      min_confidence: float = 0.5
  + AppConfig.llm: LLMConfig = LLMConfig()

src/voice_assistant/main.py
  _build():
    # After RulesRouter construction:
    if cfg.llm.enabled:
        ollama_client = OllamaClient(
            host=cfg.llm.host, model=cfg.llm.model,
            timeout_s=cfg.llm.timeout_s,
            temperature=cfg.llm.temperature,
            min_confidence=cfg.llm.min_confidence)
        nlu = LLMFallbackRouter(
            primary=nlu,
            client=ollama_client,
            commands_path=Path(config_path).parent / "commands.yaml",
            app_aliases=cfg.app_aliases)

config/default.yaml
  + llm: ...   # all defaults, enabled=false

pyproject.toml
  + ollama>=0.3

README.md
  + LLM Fallback section (setup instructions)
```

### 4.3 Data flow

```
Pipeline.process_segment (worker thread)
  transcript = asr.transcribe(...)
  intent = nlu.route(transcript)
        │
        ▼
LLMFallbackRouter.route(transcript)
  intent = self._primary.route(transcript)   # RulesRouter
  if intent.name != "unknown":
      return intent                          # fast path — no LLM
  # Slow path: LLM
  return self._client.classify(
      text=transcript.text,
      system_prompt=self._system_prompt,
  )
        │
        ▼
OllamaClient.classify(text, system_prompt) -> Intent
  if time.monotonic() < self._unreachable_until:
      return Intent.unknown()                # short-circuit
  try:
      resp = ollama.chat(
          model=self._model,
          messages=[{"role":"system","content":system_prompt},
                    {"role":"user","content":text}],
          format="json",
          options={"temperature": 0.1, "num_predict": 100},
          keep_alive="5m",
      )                                      # blocks up to timeout_s
  except ConnectionError:
      self._unreachable_until = mono + 60
      return Intent.unknown()
  except ResponseError as e if e.status_code == 404:
      self._unreachable_until = mono + 1e9   # permanent
      return Intent.unknown()
  except Timeout:
      return Intent.unknown()
  return self._parse_and_validate(resp.message.content)
```

### 4.4 `LLMFallbackRouter`

```python
class LLMFallbackRouter(NLURouter):
    def __init__(self, primary: NLURouter, client: OllamaClient,
                 commands_path: Path, app_aliases: dict[str, str]):
        self._primary = primary
        self._client = client
        catalog = _load_catalog(commands_path)
        self._system_prompt = build_system_prompt(catalog, app_aliases)
        self._catalog = catalog  # for client to validate intent names

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

### 4.5 `OllamaClient`

```python
class OllamaClient:
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
                 catalog: dict) -> Intent:
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
                         "num_predict": 100},
                keep_alive="5m",
            )
        except (ConnectionError, httpx.ConnectError) as e:
            self._mark_unreachable(60, e)
            return Intent.unknown()
        except ollama.ResponseError as e:
            if "not found" in str(e).lower() or e.status_code == 404:
                self._mark_unreachable(1e9, e, fatal=True)
            return Intent.unknown()
        except (TimeoutError, httpx.ReadTimeout):
            logger.debug(f"LLM timeout on text={text!r}")
            return Intent.unknown()
        except Exception:
            logger.exception("LLM classify unexpected error")
            return Intent.unknown()
        return self._parse_and_validate(resp.message.content, catalog)
```

### 4.6 Catalog format

```python
# From _load_catalog(commands_path):
{
    "open_app": {"slots": [("app", "string")]},
    "open_path": {"slots": [("name", "string")]},
    "minimize_all": {"slots": []},
    "volume_set": {"slots": [("level", "int")]},
    "shutdown": {"slots": [], "destructive": True},
    ...
}
```

`destructive` flag is informational only — not used to gate LLM in v1. (Could be used in a future per-intent allowlist.)

## 5. Prompt Design

### 5.1 System prompt (assembled by `prompt.build_system_prompt`)

```
Ты — классификатор голосовых команд для ПК-ассистента. Пользователь говорит фразу на русском, ты определяешь намерение и параметры.

Доступные намерения (intents):
- open_app — открыть приложение. Slot: app (string). Алиасы: телега→telegram, браузер→chrome, ...
- close_app — закрыть приложение. Slot: app (string).
- open_path — открыть папку/файл. Slot: name (string).
- open_bookmark — открыть закладку. Slot: name (string).
- open_url — открыть URL. Slot: url (string).
- web_search — поиск в Google. Slot: query (string).
- minimize_all — свернуть все окна. Без slots.
- close_window — закрыть текущее окно. Без slots.
- switch_window — переключить окно. Без slots.
- clipboard_copy / clipboard_paste / clipboard_read — буфер обмена. Без slots.
- volume_set — громкость. Slot: level (int, 0-100).
- volume_up / volume_down — громкость +/-. Без slots.
- lock_screen — заблокировать экран. Без slots.
- shutdown / reboot — выключить/перезагрузить. Без slots (потребует подтверждения).
- confirm_yes — подтверждение "да". Без slots.

Правила:
1. Отвечай ТОЛЬКО валидным JSON в формате: {"intent": "<name>", "slots": {...}, "confidence": <0.0-1.0>}
2. Если фраза не подходит ни под один intent — верни {"intent": "unknown", "slots": {}, "confidence": 0.0}
3. Confidence ≥ 0.7 если уверен, иначе ниже
4. Слот app/name/query: извлеки самое короткое осмысленное значение
5. Не добавляй лишних полей, не пиши пояснений

Примеры:
"запусти мне телегу пожалуйста" → {"intent":"open_app","slots":{"app":"telegram"},"confidence":0.9}
"скинь окошко вниз" → {"intent":"minimize_all","slots":{},"confidence":0.85}
"что в буфере" → {"intent":"clipboard_read","slots":{},"confidence":0.9}
"закрой эту хрень" → {"intent":"close_window","slots":{},"confidence":0.75}
"расскажи анекдот" → {"intent":"unknown","slots":{},"confidence":0.0}
```

The intent list is **generated** at startup from `commands.yaml` — not hardcoded. New intents added to `commands.yaml` automatically appear in the prompt. Aliases come from `cfg.app_aliases`.

### 5.2 User message

The raw transcript text. No preprocessing.

### 5.3 Ollama call options

```python
client.chat(
    model="qwen2.5:3b-instruct",
    messages=[...],
    format="json",                  # critical — guarantees valid JSON output
    options={
        "temperature": 0.1,         # near-deterministic
        "num_predict": 100,         # response budget (cap latency)
    },
    keep_alive="5m",                # keep model warm between calls
)
```

## 6. Validation (`_parse_and_validate`)

1. `json.loads(content)` — if exception → `Intent.unknown()` + DEBUG log with raw content
2. `intent_name = data["intent"]` — `KeyError` → `Intent.unknown()`
3. `intent_name in catalog` — else `Intent.unknown()` (hallucinated name)
4. `confidence = float(data["confidence"])` — `(KeyError, ValueError)` → `Intent.unknown()`
5. `confidence >= min_confidence` — else `Intent.unknown()` (silently, no log)
6. `slots = data.get("slots", {})` — must be `dict`, else `Intent.unknown()`
7. For each declared slot in `catalog[intent_name]["slots"]`:
   - Required slots present in `slots` — else `Intent.unknown()`
   - Int slots coerced via `int(slots[name])` — `ValueError` → `Intent.unknown()`
   - String slots stripped of leading/trailing whitespace
8. Return `Intent(name=intent_name, slots=slots, confidence=confidence)`

## 7. Error Handling Matrix

| Layer | Error | Action |
|---|---|---|
| `OllamaClient.classify` | `ConnectionError` (ollama not running) | WARNING once + `_unreachable_until = mono + 60`, return `Intent.unknown()` |
| `OllamaClient.classify` | `ResponseError 404` (model not pulled) | ERROR once with `ollama pull qwen2.5:3b-instruct` hint + permanent unreachable (until process restart), return `Intent.unknown()` |
| `OllamaClient.classify` | Timeout (3 s budget exhausted) | DEBUG, return `Intent.unknown()` (normal for cold start / heavy load) |
| `OllamaClient.classify` | Any other exception | `logger.exception`, return `Intent.unknown()` |
| `OllamaClient._parse_and_validate` | JSON decode error | DEBUG with raw content, return `Intent.unknown()` |
| `OllamaClient._parse_and_validate` | Missing required key | DEBUG, return `Intent.unknown()` |
| `OllamaClient._parse_and_validate` | Intent not in catalog | DEBUG with name, return `Intent.unknown()` |
| `OllamaClient._parse_and_validate` | `confidence < min_confidence` | silent, return `Intent.unknown()` |
| `OllamaClient._parse_and_validate` | Slot type mismatch / missing | DEBUG, return `Intent.unknown()` |
| `LLMFallbackRouter.__init__` | `commands.yaml` unreadable | propagate — setup failure, not runtime |
| `LLMFallbackRouter.route` | Empty transcript | short-circuit before LLM call, return primary's `unknown` |

**Invariant:** `LLMFallbackRouter.route` NEVER raises. Whatever happens at LLM layer, Pipeline gets a valid `Intent` (which is `Intent.unknown()` if the LLM didn't help). Pipeline's existing flow handles unknown → "Не понял, повтори" feedback.

## 8. Configuration

```yaml
# config/default.yaml
llm:
  enabled: false                     # OFF by default
  model: qwen2.5:3b-instruct
  host: http://localhost:11434
  timeout_s: 3.0
  temperature: 0.1
  min_confidence: 0.5
```

`enabled: false` means `_build` does NOT construct `LLMFallbackRouter` — `nlu` stays as `RulesRouter` alone. No ollama import side effects.

## 9. Setup Instructions (README addition)

```markdown
## LLM Fallback (опционально)

Если правила в `config/commands.yaml` не сматчили команду — спросить локальный LLM:

1. Установи ollama: https://ollama.com/download
2. Запусти сервер: `ollama serve` (в фоне или как сервис)
3. Спулли модель: `ollama pull qwen2.5:3b-instruct` (~2 GB)
4. В `config/default.yaml` поставь `llm.enabled: true`

LLM работает локально (по умолчанию `http://localhost:11434`). Транскрипты не уходят в облако.

Если ollama не запущена или модель не скачана — ассистент работает без LLM-fallback, без ошибок.
```

## 10. Testing Strategy

### 10.1 Mocks

- `ollama.Client.chat()` — mocked; we don't make real HTTP calls in tests
- `time.monotonic` — mocked where unreachable-cache timing is tested

### 10.2 Unit tests (≥80% coverage)

`tests/unit/nlu/test_prompt.py`:
- `build_system_prompt(catalog, aliases)` contains every intent name
- Slot type annotations correct (int vs string)
- Aliases from `cfg.app_aliases` included if non-empty
- Aliases section omitted if `app_aliases` is empty

`tests/unit/nlu/test_ollama_client.py`:
- Happy path: mock returns valid JSON → `Intent` with correct fields
- Timeout: mock raises `httpx.ReadTimeout` → `Intent.unknown()`
- ConnectionError → `Intent.unknown()` + `_unreachable_until` set to mono+60
- 404 model not found → `Intent.unknown()` + permanent unreachable
- JSON decode error → `Intent.unknown()`
- Intent name not in catalog → `Intent.unknown()`
- Confidence < min_confidence → `Intent.unknown()`
- Missing required slot → `Intent.unknown()`
- Int slot coerced from string
- Empty `slots` dict for slotless intent → accepted
- `_unreachable_until` short-circuits without HTTP call
- After 60 s elapsed → retries (and on second failure, re-sets cache)

`tests/unit/nlu/test_llm_fallback.py`:
- Primary returns known intent → LLM NOT called
- Primary returns unknown + empty text → LLM NOT called (short-circuit)
- Primary returns unknown + non-empty text → LLM called
- LLM returns valid intent → returned
- LLM returns unknown → unknown propagates
- Catalog correctly loaded from commands.yaml fixture

### 10.3 Integration test (optional)

`tests/integration/test_llm_real.py` with `@pytest.mark.requires_ollama`:
- If `OLLAMA_HOST` env var set + model available → one real call: `"включи блокнот"` → expect `open_app` (any reasonable slot)
- Skip otherwise; NOT in default suite

### 10.4 What we don't test

- Real ollama HTTP (mocked)
- LLM output quality (out of scope — depends on model + prompt)
- Real network latency (mocked)
- `qwen2.5:3b-instruct` specifically (model-agnostic at code level)

## 11. Manual Verification Checklist

Append to `README.md`:

- [ ] `llm.enabled: false` (default): assistant starts identically to before, no ollama dependency
- [ ] `llm.enabled: true` + ollama running + model pulled: rules-known command ("открой блокнот") works as before — no LLM call (verify via DEBUG log silence)
- [ ] LLM-only command ("запусти мне телегу пожалуйста"): resolved to `open_app{app="telegram"}` if alias exists, else logged DEBUG with whatever LLM picked
- [ ] LLM-only command, ambiguous ("распакуй файлик"): `Intent.unknown()` after LLM returns low confidence → "Не понял, повтори"
- [ ] ollama not running while `llm.enabled: true`: first attempt → WARNING log, subsequent attempts within 60 s → no log spam, all "Не понял, повтори"
- [ ] After 60 s + ollama restored: next unknown command tries LLM again
- [ ] Model not pulled (`ollama pull <model>` not run): ERROR log with hint, permanent unreachable for that process
- [ ] LLM-resolved destructive intent ("выключи нахрен" → `shutdown`): triggers existing confirmation flow ("вы уверены?") — destructive intents NOT bypassed

## 12. Open Questions / Future Work

- **Privacy gate** — link `store_transcripts: false` to suppress sending the transcript to ollama too (today transcripts always reach LLM if enabled). Trivial future patch.
- **Cache successful classifications** — same phrase asked twice should not re-hit LLM. ~20 LOC cache by normalized text → Intent. Defer until benchmarks show repeated phrases.
- **Per-intent allowlist** — `llm.allowed_intents: [open_app, ...]` to exclude destructive intents from LLM dispatch. Today the confirm flow protects shutdown/reboot.
- **Streaming output** — yield partial intent earlier. Probably useless since intent is determined at end of generation.
- **Custom model fine-tune** — train a tiny intent classifier on real session traces. Out of MVP/Beta scope.
- **Multi-turn dialog with memory** — separate Beta feature.

## 13. References

- ollama Python client: https://github.com/ollama/ollama-python
- ollama JSON mode: https://github.com/ollama/ollama/blob/main/docs/api.md#json-mode
- qwen2.5 family: https://qwenlm.github.io/blog/qwen2.5/
- MVP design spec: `docs/superpowers/specs/2026-05-19-voice-assistant-design.md`
- Piper TTS spec: `docs/superpowers/specs/2026-05-20-piper-tts-design.md`
