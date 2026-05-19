# Voice PC Assistant — Design Spec

**Date:** 2026-05-19
**Status:** Approved (brainstorming complete)
**Source TZ:** `voice_assistant_tz.md`

## 1. Goal & Scope

Build a desktop Python application that listens to the microphone, recognizes
speech via Whisper, maps it to intents, and executes actions on the user's PC.

The full product is delivered as **three decomposed sub-projects**, each with
its own spec → plan → implementation cycle. The core architecture is designed
upfront for all three so later stages require no rewrite.

### Sub-project 1 — MVP (this spec)
- Pipeline: `Audio Capture → VAD → Push-to-talk gate → ASR → NLU (rules) → Executor → Feedback (CLI/notifications)`
- Plugins: `apps`, `windows`, `browser`, `files`, `clipboard`, `system` (system lowest priority)
- Whisper: `device=cuda`, `compute_type=int8_float16`, model `medium` default (GPU available → WER ≤ 10% per TZ; configurable)
- Activation: push-to-talk (`Right Ctrl`)
- No GUI; file logging; YAML + pydantic config

### Sub-project 2 — Beta
Wake word (openWakeWord), Piper TTS, tray (pystray), `dictation` plugin,
LLM fallback (ollama, `qwen2.5:7b`), GUI alias settings.

### Sub-project 3 — Release
Cross-platform adapters (Linux/macOS) + installer, custom wake words,
dialog context (slot inheritance), extended plugins, auto-update.

## 2. Decisions (from TZ section 13)

| Question | Decision |
|---|---|
| Scope | Full product, decomposed into 3 sub-projects; architecture designed for all 3 |
| Primary OS | Windows (priority). Linux/macOS via `platform.py` abstraction, not verified until Release |
| GPU | NVIDIA available → `device=cuda`, `compute_type=int8_float16`, default model `medium` |
| NLU | Hybrid: rules in MVP; ollama LLM fallback added in Beta |
| Activation (MVP) | Push-to-talk (`Right Ctrl`); wake word in Beta |
| Priority plugins | apps (open/close), windows, browser+files+clipboard; system last |

## 3. Concurrency Model

**Approach A — threads + `queue.Queue`** (chosen).

Each pipeline module runs in its own thread, connected by thread-safe queues.
Whisper is heavy but the GIL is released in C extensions (CTranslate2,
sounddevice), so audio capture is not blocked. Rationale: matches TZ section 3,
simplest to test modules in isolation, GIL not a problem due to native
extensions. If profiling later shows blocking, ASR can be moved to a separate
process (multiprocessing) without rewriting the rest.

Rejected: asyncio (blocking/CPU-bound work would just wrap back to threads),
multiprocessing-everywhere (premature, costly serialization, harder debugging).

## 4. Architecture & Core Skeleton

Laid down in MVP, used by all stages:

- Each module is a class with a clear interface, runs in its own thread,
  communicates via `queue.Queue`.
- Abstract interfaces: `ASREngine`, `NLURouter`, `Activator`, `FeedbackSink` —
  so Beta/Release swap implementations without touching the core.
- `utils/platform.py` — OS detection and platform operations behind one
  interface. Windows implementation in MVP; `NotImplementedError` stubs for
  Linux/macOS until Release.
- Plugin registry via `@register_intent("...")` decorator; one plugin per file;
  core does not change when adding plugins.

### Project structure (TZ section 5, src-layout)

```
voice_assistant/
├── pyproject.toml
├── config/{default.yaml, commands.yaml}
├── src/voice_assistant/
│   ├── main.py            # pipeline assembly, graceful shutdown
│   ├── config.py          # pydantic models + YAML loading
│   ├── core/types.py      # immutable inter-module DTOs
│   ├── audio/{capture.py, vad.py}
│   ├── activation/hotkey.py        # push-to-talk (pynput)
│   ├── asr/{base.py, faster_whisper_engine.py}
│   ├── nlu/{base.py, rules.py}     # regex + rapidfuzz
│   ├── executor/{registry.py, result.py, plugins/*}
│   ├── feedback/cli.py             # stdout + plyer notifications
│   └── utils/{logging.py, platform.py}
└── tests/{unit, integration, fixtures/audio}
```

## 5. Data Flow (MVP)

1. `capture.py` — sounddevice, 16kHz mono int16, ~30s ring buffer (pre-roll).
   Pushes 30ms frames to `audio_q`.
2. `hotkey.py` — listens for `Right Ctrl`. Hold opens a "recording window":
   ring-buffer pre-roll + new frames go to `speech_q` while key is held.
3. `vad.py` — silero-vad inside the recording window, trims edge silence,
   validates min 300ms / max 15s. Assembled segment → `asr_q`.
4. `faster_whisper_engine.py` — model preloaded in memory. Returns
   `Transcript{text, lang, confidence, duration_ms}` → `nlu_q`.
5. `rules.py` — match against `commands.yaml` (regex slot templates + rapidfuzz
   threshold 85). Returns `Intent{name, slots, confidence}` → `exec_q`. No
   match → `Intent("unknown")`.
6. `registry.py` — dispatch by `intent.name` to plugin handler. Plugin returns
   `ExecutionResult{success, message, tts_response}`.
7. `feedback/cli.py` — stdout print + plyer notification, status to log.

**Data contracts** — immutable `@dataclass(frozen=True)`: `AudioSegment`,
`Transcript`, `Intent`, `ExecutionResult` in `core/types.py`.

### Plugins (MVP)

- `apps`: `open_app`, `close_app` — alias map from config (`телега→telegram`),
  launch/find via `platform.py`.
- `windows`: `minimize_all`, `close_window`, `switch_window` — pygetwindow/pywin32.
- `browser`: `web_search`, `open_url`, `open_bookmark` — webbrowser + config bookmarks.
- `files`: `open_path` — open file/folder by alias (os.startfile on Windows).
- `clipboard`: `copy`, `paste`, `read_clipboard` — pynput + clipboard read.
- `system`: `volume_set/up/down`, `lock`, `shutdown`/`reboot` (mandatory voice
  "да" confirmation, 5s timeout).

## 6. Error Handling & Edge Cases

Errors handled explicitly at every level, never swallowed; user gets a short
clear message, log gets full context.

- **No microphone / device busy:** capture catches sounddevice error at start →
  clear message + non-zero exit. Runtime device loss → ERROR log + reopen with
  backoff, status to feedback.
- **Whisper load fail / CUDA unavailable:** check CUDA at start; if `cuda`
  requested but unavailable → WARNING log + automatic fallback to `cpu`+`int8`.
- **Empty/too-short segment:** VAD discards (<300ms). Too long (>15s) → trimmed
  to limit, WARNING log (anti-loop).
- **Low ASR/NLU confidence:** `Intent("unknown")` or below threshold →
  feedback "Не понял, повтори", no action. No guessed actions.
- **Plugin error:** registry wraps handler in try/except →
  `ExecutionResult(success=False, ...)`, pipeline survives.
- **Dangerous commands** (`shutdown`/`reboot`): confirmation state — re-ask,
  wait for voice "да" with 5s timeout, else cancel.
- **Boundary validation:** config via pydantic (fail early on bad YAML); intent
  slots validated by types from `commands.yaml` before plugin call.
- **Graceful shutdown:** `main.py` catches SIGINT/Ctrl+C → sentinel to all
  queues, threads finish, model unloaded, audio resources released.

## 7. Testing

Target ≥ 80% coverage, TDD (tests first).

- **Unit:**
  - `nlu/rules.py` — ≥5 phrases per intent (RU+EN), slot extraction, fuzzy
    threshold, rejection on garbage.
  - Each executor plugin — platform calls mocked (pyautogui/pynput/os.startfile),
    verify intent→action mapping and `ExecutionResult`.
  - `config.py` — valid/invalid YAML, defaults.
  - DTO immutability.
- **Integration:** reference wavs in `tests/fixtures/audio/` through the full
  pipeline (capture mocked with wav source), assert final intent. Dangerous
  commands — execution mocked, confirmation flow verified.
- **E2E/manual:** ~30-command checklist per stage release (documented).
- **Performance:** `scripts/benchmark_asr.py` — latency (end of phrase → action
  start, target ≤ 1.5s) and WER across models.
- **CI:** pytest + pytest-asyncio, runs on Windows; platform-dependent tests
  marked with markers.

## 8. Non-Functional Requirements (from TZ section 2)

- Latency end-of-phrase → command start ≤ 1.5s on mid machine.
- WER ≤ 10% RU with `medium`/`large-v3`.
- Fully offline for core scenarios; online only optional (web tasks, LLM mode).
- RU + EN (Whisper multi-lang).
- Extensibility: new command = one plugin file, no core change.
- Privacy: audio stays local; transcript logging fully disableable.
