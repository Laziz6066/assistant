# Dictation Mode — Design Spec

**Date:** 2026-05-20
**Status:** Approved, ready for implementation plan
**Sub-project:** Beta (post-MVP, post-Piper-TTS, post-ollama, post-wake-word, post-tray, post-multi-turn-dialog)
**Depends on:** voice-assistant branch at commit `42d47dd` or later

## 1. Goal

Add a dictation mode toggleable by voice ("режим диктовки" / "стоп диктовка"). While active, transcripts skip NLU and are typed verbatim into the active window via keyboard injection, with a small set of Russian punctuation words (`точка → .`, `запятая → ,`, `новая строка → \n`, …) translated to symbols.

## 2. Scope

**In:**
- Voice toggle: new intents `start_dictation`, `stop_dictation` in `commands.yaml`
- `ModeStore`: small thread-safe state machine (`"command" | "dictation"`)
- `DictationProcessor`: normalizes transcript text and calls `platform_ops.type_text(...)`
- `normalize_punctuation(text)`: pure function with 10-entry punctuation map
- `PlatformOps.type_text(text)`: keyboard injection via pynput; Windows-first, gracefully degrades on unsupported platforms
- Plugin handlers `start_dictation` / `stop_dictation` that toggle `ctx.mode_store`
- `DictationConfig.enabled`, `DictationConfig.type_delay_s`; default `enabled: true`
- Pipeline integration: when in dictation mode, bypass NLU dispatch (except for `stop_dictation`) and route to `DictationProcessor`
- Skip `ContextStore.add` while in dictation mode (multi-turn doesn't track dictated text)

**Out (deferred):**
- Real-time partial dictation (we still wait for end-of-utterance VAD)
- Sentence capitalization heuristics ("привет" → "Привет" at start of sentence)
- Selective replacement (only when preceded by space, etc.) — current regex is good enough for v1
- Voice-driven editing ("удали последнее предложение")
- Multiple cursor / structured editor support
- Linux/macOS keyboard injection — pynput supports them, but untested
- Click-aware injection (paste into specific UI control by name)
- Custom user-defined punctuation map via config

## 3. Decisions

| Question | Decision |
|---|---|
| Mode toggle mechanism | Voice intents `start_dictation` / `stop_dictation` (added to `commands.yaml`) |
| Output method | Keyboard injection via `pynput.keyboard.Controller.type(...)` |
| Punctuation handling | Fixed 10-entry map; longest-phrase-first replacement; whitespace tightening |
| Default `enabled` | `true` (low risk — only fires after explicit voice activation) |
| In-dictation NLU policy | Always route through NLU; only `stop_dictation` matches trigger dispatch; everything else feeds the processor |
| Failure policy | Any pynput / platform failure logged and swallowed; pipeline continues |
| Multi-turn context interaction | While in dictation, successful "dispatches" (only `stop_dictation`) are NOT added to `ContextStore` |
| TTS-feedback while dictating | Silent — the keystrokes themselves are the user-visible feedback; loguru INFO logs char count |

## 4. Architecture

### 4.1 New files

```
src/voice_assistant/dictation/
  __init__.py
  mode_store.py          # ModeStore — state + Lock
  punctuation.py         # normalize_punctuation(text) — pure function
  processor.py           # DictationProcessor(platform_ops)

src/voice_assistant/executor/plugins/
  dictation.py           # start_dictation / stop_dictation plugin handlers
```

### 4.2 Modified files

```
src/voice_assistant/config.py
  + class DictationConfig(BaseModel): enabled: bool = True; type_delay_s: float = 0.01
  + AppConfig.dictation

src/voice_assistant/executor/context.py
  + ExecutorContext.mode_store: ModeStore | None

src/voice_assistant/executor/plugins/__init__.py
  + register_all() now also imports & registers dictation plugin

src/voice_assistant/utils/platform.py
  + PlatformOps.type_text(text: str)
  + Windows impl uses pynput.keyboard.Controller().type(text)
  + Default impl logs warning + raises NotImplementedError

src/voice_assistant/main.py
  Pipeline gains: mode_store: ModeStore | None
                  dictation_processor: DictationProcessor | None
  process_segment branches on mode (see §4.5)
  ExecutorContext built with mode_store kwarg
  _build constructs ModeStore + DictationProcessor when cfg.dictation.enabled
  Skip context_store.add when in dictation mode

config/commands.yaml
  + intent: start_dictation (examples: "начни диктовать", "режим диктовки", "диктуй")
  + intent: stop_dictation  (examples: "стоп диктовка", "конец диктовки", "выход из диктовки", "выход")
  NOTE: ordering matters — put these BEFORE generic open/close so they don't get
  eaten by greedy slot regex.

config/default.yaml
  + dictation: ...

README.md
  + Dictation section + manual checklist
```

### 4.3 `ModeStore` interface

```python
class ModeStore:
    """Thread-safe state machine for assistant operating mode.

    Modes:
      "command"  — default. Pipeline dispatches intents normally.
      "dictation" — Pipeline routes transcripts to DictationProcessor.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode = "command"

    def is_dictation(self) -> bool: ...
    def is_command(self) -> bool: ...
    def start_dictation(self) -> None: ...  # idempotent
    def stop_dictation(self) -> None: ...   # idempotent
    def current_mode(self) -> str: ...
```

### 4.4 `DictationProcessor` interface

```python
class DictationProcessor:
    """Owns the normalize-then-type pipeline. Swallows platform failures."""

    def __init__(self, platform_ops) -> None:
        self._ops = platform_ops

    def type_transcript(self, transcript_text: str) -> None:
        """Normalize punctuation and inject as keystrokes.

        On platform error: log exception, do not raise.
        Empty / whitespace-only transcript: no-op.
        """
```

### 4.5 Pipeline integration

```python
def process_segment(self, segment: AudioSegment) -> None:
    transcript = self.asr.transcribe(segment)
    # existing privacy-aware ASR log unchanged

    if transcript.confidence < self.config.asr.min_confidence \
            or not transcript.text.strip():
        self.feedback.emit("Не понял, повтори", success=False)
        return

    intent = self.nlu.route(transcript)

    # Dictation branch
    if self.mode_store is not None and self.mode_store.is_dictation():
        if intent.name == "stop_dictation":
            # Let the plugin toggle the mode flag back to "command"
            result = self.registry.dispatch(intent, self.ctx)
            self.feedback.emit(result.tts_response, success=result.success)
            return
        # Everything else in dictation mode → type the transcript
        if self.dictation_processor is not None:
            self.dictation_processor.type_transcript(transcript.text)
        logger.info(f"dictated: {len(transcript.text)} chars")
        return

    # Command branch (existing)
    if intent.name == "unknown":
        self.feedback.emit("Не понял, повтори", success=False)
        return
    result = self.registry.dispatch(intent, self.ctx)
    logger.info(f"intent={intent.name} success={result.success}")
    if result.success and self.context_store is not None:
        self.context_store.add(intent)
    self.feedback.emit(result.tts_response, success=result.success)
```

### 4.6 Plugin handlers

```python
# src/voice_assistant/executor/plugins/dictation.py
def _start_dictation(slots, ctx) -> ExecutionResult:
    if ctx.mode_store is None:
        return ExecutionResult.fail("Режим диктовки выключен в config")
    ctx.mode_store.start_dictation()
    return ExecutionResult.ok("Режим диктовки", tts_response="Режим диктовки")


def _stop_dictation(slots, ctx) -> ExecutionResult:
    if ctx.mode_store is None:
        return ExecutionResult.ok("ok", tts_response="Готово")
    ctx.mode_store.stop_dictation()
    return ExecutionResult.ok("ok", tts_response="Готово")


def register(reg: Registry) -> None:
    reg.add("start_dictation", _start_dictation)
    reg.add("stop_dictation", _stop_dictation)
```

### 4.7 `PlatformOps.type_text`

```python
class WindowsPlatformOps:  # (or whichever the existing class is named)
    def type_text(self, text: str) -> None:
        if not text:
            return
        try:
            from pynput.keyboard import Controller
            Controller().type(text)
        except Exception:
            logger.exception(f"type_text failed for {len(text)} chars")
            raise


class DefaultPlatformOps:
    def type_text(self, text: str) -> None:
        logger.warning("type_text not implemented on this platform")
        raise NotImplementedError("type_text")
```

`DictationProcessor.type_transcript` catches the raised exception so the pipeline does not see it.

## 5. Punctuation Normalization

```python
_PUNCT: dict[str, str] = {
    # multi-word entries are tried first; sort by length descending
    "точка с запятой": ";",
    "восклицательный знак": "!",
    "точка": ".",
    "запятая": ",",
    "вопрос": "?",
    "восклицательный": "!",
    "двоеточие": ":",
    "тире": "—",
    "дефис": "-",
    "новая строка": "\n",
}
```

### 5.1 Algorithm

```python
def normalize_punctuation(text: str) -> str:
    out = text
    # Longest phrase first so "точка с запятой" wins over "точка"
    for word in sorted(_PUNCT.keys(), key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(word)}\b", _PUNCT[word], out,
                      flags=re.IGNORECASE)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)  # no space before punctuation
    out = re.sub(r"\s+\n", "\n", out)
    out = re.sub(r"\n\s+", "\n", out)
    out = re.sub(r"[ \t]+", " ", out)
    return out.strip()
```

### 5.2 Worked examples

| Input | Output |
|---|---|
| `"привет мама точка"` | `"привет мама."` |
| `"сколько времени вопрос"` | `"сколько времени?"` |
| `"первая строка новая строка вторая"` | `"первая строка\nвторая"` |
| `"тест точка с запятой следующее"` | `"тест; следующее"` |
| `"не имеет точки"` | `"не имеет точки"` (word `точки` ≠ `точка`) |
| `"восклицательный знак"` | `"!"` |
| `"молоко запятая хлеб запятая сахар"` | `"молоко, хлеб, сахар"` |
| `"восток"` | `"восток"` (`\b` prevents partial match) |

## 6. Configuration

```yaml
# config/default.yaml
dictation:
  enabled: true
  type_delay_s: 0.01
```

`enabled: false` → `_build` constructs neither `ModeStore` nor `DictationProcessor`, and the `start_dictation` plugin handler returns "Режим диктовки выключен" because `ctx.mode_store is None`.

```yaml
# config/commands.yaml — ADD at the start (before "открой {app}")
- intent: start_dictation
  examples: ["начни диктовать", "режим диктовки", "диктуй"]
  slots: {}
- intent: stop_dictation
  examples: ["стоп диктовка", "конец диктовки", "выход из диктовки", "выход"]
  slots: {}
```

Order matters: these intents have literal-token prefixes (`диктуй`, `стоп диктовка`, `режим диктовки`) so they do NOT conflict with `open_app / close_app` greedy patterns. They can go anywhere in the file, but consistency with existing convention (specific before generic) suggests putting them near the top.

## 7. Error Handling

| Layer | Error | Behaviour |
|---|---|---|
| `ModeStore.start_dictation/stop_dictation` | Concurrent toggle from worker + plugin | Lock serializes |
| `normalize_punctuation` | Non-str input | `TypeError` (caller must pass str — Pipeline always does) |
| `DictationProcessor.type_transcript` | `platform_ops.type_text` raises | `logger.exception`, return cleanly |
| `DictationProcessor.type_transcript` | Empty / whitespace-only text | No-op (no platform call) |
| `PlatformOps.type_text` (Windows) | pynput not installed | Lazy import raises `ImportError` → propagated to processor → caught |
| `PlatformOps.type_text` (Windows) | Secure desktop / UAC blocks injection | pynput raises → caught in processor |
| Pipeline w/ `mode_store=None` | start_dictation intent dispatched | Plugin returns "Режим диктовки выключен" |
| Pipeline w/ `dictation_processor=None` + in-dictation-mode somehow | Should be impossible (both built together), but defensive: skip `type_transcript` call (the `if self.dictation_processor is not None` guard in §4.5) |
| User invokes `stop_dictation` while in command mode | Plugin idempotent — already in command — returns "Готово" |
| ASR low confidence | Existing gate fires BEFORE the dictation branch — no transcript leaks |

**Invariant:** dictation failures never propagate to the worker. The keystrokes ARE the feedback — if they fail silently, the user notices (no text appears) and tries again or says "стоп диктовка".

## 8. Testing Strategy

### 8.1 Mocks

- `pynput.keyboard.Controller` — patched at `voice_assistant.utils.platform.Controller` (or wherever lazy import lands) to avoid touching real keyboard in CI
- Real `threading.Lock` for ModeStore tests
- `time.sleep` not mocked — tests are fast enough not to care about `type_delay_s`

### 8.2 Unit tests (~25-28)

`tests/unit/dictation/test_mode_store.py` (~5):
- Default state is "command"
- `start_dictation()` switches to "dictation"
- `stop_dictation()` switches back to "command"
- Idempotent — double `start_dictation()` doesn't error
- Lock serializes concurrent toggles (smoke test with two threads)

`tests/unit/dictation/test_punctuation.py` (~12):
- Each single-word symbol mapping
- Multi-word: "точка с запятой" → ";"
- Multi-word: "восклицательный знак" → "!"
- No-match: "точки" not replaced
- Case-insensitive: "Точка" → "."
- Word boundary: "восток" not partially replaced
- Space tightening: "привет , мир" → "привет, мир"
- Newline tightening
- Whitespace collapse
- Empty string → ""
- Mixed Russian/English text passes through
- Multiple sentences

`tests/unit/dictation/test_processor.py` (~3):
- `type_transcript` normalizes then types
- Empty transcript → no platform call
- `platform_ops.type_text` raising is caught (no propagate)

`tests/unit/executor/plugins/test_dictation.py` (~3):
- `start_dictation` handler calls `ctx.mode_store.start_dictation()` + returns success
- `stop_dictation` handler calls `ctx.mode_store.stop_dictation()` + returns success
- Handlers return `mode_store is None` gracefully

`tests/unit/test_main.py` extend (~3):
- Pipeline in dictation mode + non-stop intent → `dictation_processor.type_transcript` called
- Pipeline in dictation mode + `stop_dictation` intent → `registry.dispatch` called (plugin toggles mode)
- Pipeline in command mode → existing behavior unchanged

`tests/unit/utils/test_platform.py` extend (~2):
- `type_text` calls pynput Controller.type (mocked)
- `type_text` on default (non-Windows) platform raises NotImplementedError

`tests/unit/test_config.py` extend (~2):
- `DictationConfig` defaults
- `AppConfig.dictation` integration

### 8.3 Integration test

`tests/integration/test_dictation.py`:
- Real `RulesRouter` + `ModeStore` + `DictationProcessor` (with mocked platform_ops)
- 3-turn scenario:
  1. "режим диктовки" → `mode_store.is_dictation()` is True
  2. "привет мама точка" → `ops.type_text("привет мама.")` called
  3. "стоп диктовка" → mode back to "command"
- Verify multi-turn context_store NOT updated during dictation

### 8.4 What we don't test

- Real keystroke injection (CI has no UI)
- Cross-platform keyboard layouts
- Performance of pynput typing under load
- Real pynput permission errors on macOS / Linux

## 9. README additions

```markdown
## Dictation mode (надиктовка)

Скажи "режим диктовки" / "начни диктовать" / "диктуй" — ассистент перейдёт в режим диктовки. Дальше всё, что ты говоришь, печатается в активное окно (документ, email, чат). Знаки препинания произноси словами: `точка, запятая, вопрос, восклицательный, двоеточие, тире, дефис, точка с запятой, новая строка`.

Чтобы выйти: "стоп диктовка" / "конец диктовки" / "выход".

Пример:
```
ты: режим диктовки
ассистент: Режим диктовки

ты:  привет мама точка как у тебя дела вопрос
напечатано: привет мама. как у тебя дела?

ты: стоп диктовка
ассистент: Готово
```

Отключить весь режим: `dictation.enabled: false` в `config/default.yaml` (фраза "режим диктовки" будет давать "Режим диктовки выключен").
```

## 10. Manual Verification Checklist

Append to `README.md`:

- [ ] "режим диктовки" → TTS подтверждает + mode switch
- [ ] "привет всем точка" → "привет всем." напечатано в активном Notepad/Word
- [ ] "новая строка" → перевод строки
- [ ] "сколько времени вопрос" → "сколько времени?"
- [ ] "молоко запятая хлеб запятая сахар" → "молоко, хлеб, сахар"
- [ ] "стоп диктовка" → выход, обычные команды снова работают
- [ ] Длинная фраза (50+ слов) печатается полностью без потерь
- [ ] `dictation.enabled: false` → "режим диктовки" не активирует mode
- [ ] Multi-turn context (если ENABLE'д) НЕ обновляется во время диктовки — после "стоп" обычное "закрой его" не находит контекст из dictated text

## 11. Open Questions / Future Work

- **Auto-capitalize first word of sentence** — `"я хочу точка ты тоже"` → `"я хочу. Ты тоже"` (capital T). Trivial post-step.
- **Dictation + multi-turn integration** — currently dictation skips ContextStore. Could store the dictation text itself as a "what I just typed" memory for follow-up commands ("удали последнее"). Big design.
- **Per-app punctuation profiles** — code editors might want different symbols ("открывающая скобка" → "(", "точка с запятой" → ";"). Defer until a real use-case emerges.
- **Inverse: "what did I just say"** — useful for confirmation before paste. Not v1.
- **Continuous dictation without VAD pauses** — would need streaming ASR. Defer.
- **Click-to-target dictation** — "напиши в окне Word..." requires window detection.
- **Configurable punctuation map** via YAML — easy extension once usage patterns emerge.

## 12. References

- pynput Controller.type: https://pynput.readthedocs.io/en/latest/keyboard.html
- MVP spec: `docs/superpowers/specs/2026-05-19-voice-assistant-design.md`
- Multi-turn dialog spec (closest sibling pattern): `docs/superpowers/specs/2026-05-20-multi-turn-dialog-design.md`
- ollama LLM fallback spec (Pipeline-integration sibling): `docs/superpowers/specs/2026-05-20-ollama-fallback-design.md`
