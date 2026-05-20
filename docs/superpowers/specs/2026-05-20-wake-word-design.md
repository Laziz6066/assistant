# Wake Word — Design Spec

**Date:** 2026-05-20
**Status:** Approved, ready for implementation plan
**Sub-project:** Beta (post-MVP, post-Piper-TTS, post-ollama-fallback)
**Depends on:** voice-assistant branch at commit `9dbce26` or later

## 1. Goal

Add an always-on wake-word detector so users can trigger the assistant by saying a wake phrase (default: "hey jarvis") instead of holding the push-to-talk key. PTT remains available as a parallel activator — both work simultaneously.

## 2. Scope

**In:**
- `WakeWordActivator(Activator)` — new Activator that runs openWakeWord on the live audio stream
- `CompositeActivator(Activator)` — fan-out that lets PushToTalk and WakeWordActivator run side-by-side
- Audio pub/sub: `AudioCapture.subscribe(callback)` so multiple consumers (PTT ring + wake) get the same chunks
- Wake model lifecycle: lazy download via openWakeWord on first run
- VAD-based end-of-speech detection (800 ms silence, 10 s max ceiling)
- `WakeConfig` in `config.py`, `enabled: false` by default
- Reuses the existing `on_state_change(bool)` callback closure that PTT uses — same ring-mark/snapshot/speech_q flow

**Out (deferred):**
- Custom Russian wake-word model training (separate sub-project)
- VAD-during-IDLE (only run wake detection when speech is present) — costs CPU, defer
- Voice fingerprinting for false-positive reduction
- Echo-cancellation against TTS audio (we just reset wake state after each detection)
- Multiple simultaneous wake words from one model
- Continuous attention mode ("no wake needed for next 30s after previous command")

## 3. Decisions

| Question | Decision |
|---|---|
| Coexist with PTT? | Yes — both work simultaneously via `CompositeActivator` |
| Library | openWakeWord (open-source, CPU-friendly, ONNX, ~8 MB total models) |
| Default wake phrase | `hey_jarvis` (pretrained, swappable via config) |
| Activation cutoff | VAD silence (800 ms) + 10 s ceiling (Siri-style) |
| Default `enabled` | `false` (user opts in; always-on inference costs ~5 % CPU) |
| Model storage | `~/.voice-assistant/wake-models/` (override via `cfg.wake.models_dir`) |
| Audio sharing | New `AudioCapture.subscribe(callback)` — minimal pub/sub addition |
| Threading | Wake detector runs its own daemon thread; subscriber callback (sounddevice thread) only does `queue.put_nowait` |
| Failure policy | Any model/load failure → wake disabled, log error, PTT continues unchanged |
| Concurrent activation | If PTT held while wake fires (or vice-versa), the second event is ignored — log DEBUG |

## 4. Architecture

### 4.1 New files

```
src/voice_assistant/activation/
  composite.py        # CompositeActivator(Activator) — fan-out lifecycle
  wake_word.py        # WakeWordActivator(Activator) — openWakeWord + VAD-based release
  models_store.py     # WakeModelStore — built-in alias lookup + lazy download
```

### 4.2 Modified files

```
src/voice_assistant/audio/capture.py
  AudioCapture gains subscribe(callback) / unsubscribe(callback). Existing
  ring.extend() path unchanged — PTT continues to work via snapshot.

src/voice_assistant/config.py
  + class WakeConfig(BaseModel): ...
  + AppConfig.wake: WakeConfig = WakeConfig()

src/voice_assistant/main.py
  _build() now collects a list of activators and either uses the single
  PushToTalk or wraps both in CompositeActivator. Wake construction
  guarded by cfg.wake.enabled; failure (e.g. model download) drops wake
  from the list but keeps PTT.

pyproject.toml
  + openwakeword>=0.6
```

### 4.3 `AudioCapture` pub/sub (the only change to existing code)

```python
class AudioCapture:
    def __init__(self, sample_rate, ring_seconds, device):
        # ... existing ...
        self._subscribers: list[Callable[[np.ndarray], None]] = []
        self._sub_lock = threading.Lock()

    def subscribe(self, cb: Callable[[np.ndarray], None]) -> None:
        with self._sub_lock:
            self._subscribers.append(cb)

    def unsubscribe(self, cb: Callable[[np.ndarray], None]) -> None:
        with self._sub_lock:
            if cb in self._subscribers:
                self._subscribers.remove(cb)

    def start(self):
        import sounddevice as sd

        def _cb(indata, frames, time, status):
            if status:
                logger.warning(f"audio status: {status}")
            chunk = indata[:, 0].copy()
            self.ring.extend(chunk)
            with self._sub_lock:
                subs = list(self._subscribers)
            for cb in subs:
                try:
                    cb(chunk)
                except Exception:
                    logger.exception("audio subscriber failed")

        # ... existing InputStream construction ...
```

**Invariant:** subscribers must return in < 5 ms or sounddevice drops frames. `WakeWordActivator._on_audio_chunk` only does `queue.put_nowait`.

### 4.4 `CompositeActivator`

```python
class CompositeActivator(Activator):
    """Fan-out Activator. start/stop are called on every child in order;
    one child raising doesn't abort the rest."""

    def __init__(self, activators: Sequence[Activator]) -> None:
        self._activators = list(activators)

    def start(self) -> None:
        for a in self._activators:
            try:
                a.start()
            except Exception:
                logger.exception(
                    f"activator {type(a).__name__} start failed")

    def stop(self) -> None:
        for a in self._activators:
            try:
                a.stop()
            except Exception:
                logger.exception(
                    f"activator {type(a).__name__} stop failed")
```

### 4.5 `WakeWordActivator`

```python
class WakeWordActivator(Activator):
    """Always-on wake-word detector wired to AudioCapture.

    State machine:
      IDLE       — feed audio to openWakeWord, watch for score > threshold
      COLLECTING — speech is being captured (PTT-equivalent); end on
                   silence (silence_ms) or max ceiling (max_speech_ms)
    """

    def __init__(self, *, model: str, store: WakeModelStore,
                 capture: AudioCapture,
                 threshold: float, silence_ms: int, max_speech_ms: int,
                 on_state_change: Callable[[bool], None]) -> None:
        self._model_name = model
        self._store = store
        self._capture = capture
        self._threshold = threshold
        self._silence_ms = silence_ms
        self._max_speech_ms = max_speech_ms
        self._on_state_change = on_state_change

        self._audio_q: queue.Queue = queue.Queue(maxsize=16)
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._available = False
        self._model = None  # openwakeword.Model, set in start()

    def start(self) -> None:
        try:
            onnx_path = self._store.ensure(self._model_name)
        except WakeModelNotFoundError as e:
            logger.error(f"wake disabled — model unavailable: {e}")
            self._available = False
            return
        try:
            from openwakeword.model import Model
            self._model = Model(wakeword_models=[str(onnx_path)],
                                  inference_framework="onnx")
        except Exception as e:
            logger.error(f"wake disabled — engine load failed: {e}")
            self._available = False
            return
        self._capture.subscribe(self._on_audio_chunk)
        self._available = True
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                         name="WakeWordActivator._worker")
        self._thread.start()
        logger.info(f"wake-word armed: {self._model_name} "
                    f"(threshold={self._threshold})")

    def stop(self) -> None:
        if self._available:
            self._capture.unsubscribe(self._on_audio_chunk)
        self._stop_evt.set()
        try:
            self._audio_q.put_nowait(_STOP)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _on_audio_chunk(self, chunk: np.ndarray) -> None:
        # sounddevice callback thread — MUST be fast
        try:
            self._audio_q.put_nowait(chunk)
        except queue.Full:
            logger.debug("wake _audio_q full, dropping chunk")

    def _worker(self) -> None:
        state = "IDLE"
        collecting_ms = 0
        silence_ms = 0
        # ... see Section 5 for state machine details ...
```

State machine details live in Section 5.

### 4.6 `WakeModelStore`

```python
class WakeModelNotFoundError(Exception):
    """Raised when an aliased model isn't available and can't be downloaded."""


class WakeModelStore:
    """Resolve a wake-word model name to a local .onnx path.

    Built-in aliases are downloaded via openWakeWord's bundled downloader.
    Custom models (passed as absolute paths) are loaded as-is.
    """

    BUILTIN_ALIASES = {
        "hey_jarvis":  "hey_jarvis_v0.1.onnx",
        "alexa":       "alexa_v0.1.onnx",
        "computer":    "computer_v0.1.onnx",
        "hey_mycroft": "hey_mycroft_v0.1.onnx",
    }
    # NOTE: the exact filenames written by openWakeWord's download_models()
    # may differ slightly between library versions. The implementer must
    # verify the actual files in `<models_dir>` after one download and
    # adjust BUILTIN_ALIASES values to match. The alias keys (hey_jarvis,
    # alexa, ...) stay the same — they're the names users put in config.

    def __init__(self, models_dir: Path):
        self._dir = Path(models_dir).expanduser()
        self._dir.mkdir(parents=True, exist_ok=True)

    def ensure(self, model: str) -> Path:
        # 1. Absolute path to .onnx provided directly
        p = Path(model)
        if p.suffix == ".onnx" and p.is_file():
            return p
        # 2. Built-in alias
        if model in self.BUILTIN_ALIASES:
            target = self._dir / self.BUILTIN_ALIASES[model]
            if not target.is_file():
                self._download_builtin(model)
            if not target.is_file():
                raise WakeModelNotFoundError(
                    f"download succeeded but {target} not found")
            return target
        raise WakeModelNotFoundError(
            f"unknown wake-word model: {model!r} "
            f"(known aliases: {list(self.BUILTIN_ALIASES)})")

    def _download_builtin(self, alias: str) -> None:
        from openwakeword.utils import download_models
        try:
            download_models(
                model_names=[alias],
                target_directory=str(self._dir),
            )
        except Exception as e:
            raise WakeModelNotFoundError(
                f"failed to download {alias}: {e}") from e
```

`openwakeword.utils.download_models()` also downloads the two shared feature-extractor ONNX files (`melspectrogram.onnx`, `embedding_model.onnx`) automatically into the same directory the first time it runs.

## 5. State Machine

```
                        ┌────────┐
              ┌────────►│  IDLE  │
              │         └────┬───┘
              │              │ score > threshold
              │              ▼
              │     ┌──────────────┐
              │     │  on_state_   │
              │     │  change(True)│
              │     └──────┬───────┘
              │            │
              │            ▼
              │    ┌─────────────────┐
              │    │   COLLECTING    │
              │    │ silence_ms = 0  │
              │    │ collecting_ms=0 │
              │    └────────┬────────┘
              │             │
              │   each chunk:
              │   collecting_ms += chunk_ms
              │   if loud:
              │       silence_ms = 0
              │   else:
              │       silence_ms += chunk_ms
              │
              │   exit if:
              │     silence_ms >= self.silence_ms          (800 ms default)
              │     collecting_ms >= self.max_speech_ms    (10000 ms)
              │
              │            │
              │            ▼
              │  ┌────────────────────┐
              │  │ on_state_change    │
              │  │ (False)            │
              │  │ self._model.reset_ │
              │  │ prediction_buffer()│
              │  └────────┬───────────┘
              │           │
              └───────────┘
```

**"loud" definition:** the chunk's RMS energy exceeds a small threshold (e.g. peak amplitude > 200 in int16 ≈ silence floor). This is a simple heuristic, not a full VAD model — keeps the loop CPU-cheap. Borrowing silero would be overkill and adds dependency on its model loader inside the wake thread; the existing `VADSegmenter` runs later in the pipeline anyway.

Energy threshold tunable indirectly via `silence_ms` (longer silence_ms tolerates more background noise).

**Per-chunk math:** at 16 kHz mono int16, sounddevice typically delivers chunks of 1280 samples (80 ms). State machine advances per chunk.

**Wake re-trigger guard:** at the COLLECTING → IDLE transition we call `self._model.reset_prediction_buffer()` so the buffered features from "hey jarvis" don't re-trigger immediately on the same audio after returning to IDLE.

**TTS-echo guard (future):** we don't suppress wake during TTS playback in v1. The COLLECTING-state reset above prevents the most common re-trigger pattern (assistant repeats wake-word as part of its response). Documented as Open Question §11.

## 6. Configuration

```yaml
# config/default.yaml
wake:
  enabled: false                       # OFF by default
  model: hey_jarvis                    # alias or absolute .onnx path
  threshold: 0.5                       # 0.0–1.0; lower → more false-positives
  silence_ms: 800                      # silence to detect end of command
  max_speech_ms: 10000                 # safety cutoff
  models_dir: ~/.voice-assistant/wake-models
```

`enabled: false` means `_build` does not import `openwakeword` and does not construct `WakeWordActivator`. No CPU cost, no model download.

## 7. Error Handling

| Layer | Error | Behaviour |
|---|---|---|
| `WakeModelStore.ensure()` | Unknown alias | `WakeModelNotFoundError` |
| `WakeModelStore.ensure()` | Network unavailable for built-in download | `WakeModelNotFoundError` |
| `WakeWordActivator.start()` | `openwakeword` import error | log ERROR, `_available=False`, return cleanly; PTT still works |
| `WakeWordActivator.start()` | Model load failure (corrupt ONNX) | same |
| `WakeWordActivator.start()` | `WakeModelNotFoundError` | same |
| `WakeWordActivator._worker()` | `model.predict()` raises (tensor shape mismatch, etc.) | log exception, continue worker loop |
| `WakeWordActivator._worker()` | Detection during PTT-held (concurrent) | log DEBUG, ignore (the existing on_state_change closure already gated on `mark`) |
| `WakeWordActivator._on_audio_chunk()` | `queue.Full` | DEBUG, drop chunk (16-deep queue = ~1.3 s buffered; if behind by that much, we're broken) |
| `AudioCapture._cb` | Subscriber raises | logger.exception, continue to next subscriber (already in spec §4.3) |
| `CompositeActivator.start/stop` | A child raises | log + continue with remaining children |

**Invariant:** any failure in the wake-word path leaves PTT fully functional. The pipeline worker thread (`main._worker`) never observes wake-specific failures.

## 8. Testing Strategy

### 8.1 Mocks

- `openwakeword.model.Model` — mocked at `voice_assistant.activation.wake_word.Model`. `predict()` returns a dict keyed by model name, value = score.
- `openwakeword.utils.download_models` — mocked in `WakeModelStore` tests.
- Real `threading`, `queue` — synchronization is part of what's tested.
- Real `numpy` arrays for chunks; synthetic int16 samples.

### 8.2 Unit tests (target ≥ 80 % coverage on new modules)

`tests/unit/audio/test_capture.py` (extend):
- `subscribe()` adds the callback; `unsubscribe()` removes it
- `_cb` calls all subscribers in order with the chunk numpy array
- One subscriber raising does NOT prevent later subscribers from being called
- After `unsubscribe`, the callback is no longer invoked

`tests/unit/activation/test_composite.py`:
- `start()` fans out to all children
- `stop()` fans out
- One child's `start` raising does not abort others
- Same for `stop`

`tests/unit/activation/test_models_store.py`:
- `ensure("hey_jarvis")` returns `<dir>/hey_jarvis_v0.1.onnx` (with file pre-created in tmp_path)
- `ensure("/abs/path/to/custom.onnx")` returns the path verbatim when the file exists
- Unknown alias → `WakeModelNotFoundError`
- Missing built-in file triggers `_download_builtin` (mock)
- `_download_builtin` raising propagates as `WakeModelNotFoundError`

`tests/unit/activation/test_wake_word.py` (~12 tests):
- `start()` resolves model, subscribes to capture, sets `_available=True`, spawns thread
- `start()` swallows `WakeModelNotFoundError` → `_available=False`, no thread, no raise
- `start()` swallows model load errors → `_available=False`
- IDLE: low-score chunk → no state transition, no callback
- IDLE: high-score chunk → `on_state_change(True)` called once, state = COLLECTING
- COLLECTING: continued loud chunks → no transition, silence_ms stays 0
- COLLECTING: silent chunks accumulate → at silence_ms ≥ 800, `on_state_change(False)` + back to IDLE
- COLLECTING: long speech → at collecting_ms ≥ 10000, `on_state_change(False)` + back to IDLE
- COLLECTING: wake detection re-fires → ignored (state machine guard)
- `model.predict()` raising → worker logs exception, continues
- `_audio_q` full → `_on_audio_chunk` doesn't block, drops with DEBUG
- `stop()` joins thread within 2 s; calls `capture.unsubscribe`
- COLLECTING → IDLE transition calls `model.reset_prediction_buffer()`

`tests/unit/test_main.py` (extend):
- `_build` with `wake.enabled: true` constructs `CompositeActivator([PushToTalk, WakeWordActivator])`
- `_build` with `wake.enabled: false` returns plain `PushToTalk` (no Composite wrapping)
- `_build` with `wake.enabled: true` but `WakeModelStore.ensure` raises → falls back to plain `PushToTalk` (graceful degrade)

### 8.3 Integration test (optional)

`tests/integration/test_wake_real.py` with `@pytest.mark.requires_wake_model`:
- If `~/.voice-assistant/wake-models/hey_jarvis_v0.1.onnx` exists, feed a synthetic wake .wav and assert detection. Skip otherwise.

### 8.4 What we don't test

- Real audio device (sounddevice fully mocked in capture tests)
- openWakeWord internals (upstream)
- Actual download from openWakeWord's CDN (mocked)
- Real wake-word audio recognition quality (manual checklist territory)

## 9. Setup Instructions (README addition)

```markdown
## Wake word (опционально)

Параллельно с PTT можно активировать ассистента голосом — скажи "hey jarvis" и
дальше команду.

1. Включи в `config/default.yaml`: `wake.enabled: true`
2. Запусти ассистента — модель (~8 MB) скачается с openWakeWord CDN при первом старте

Все модели локальные, аудио не покидает машину.

Если `openwakeword` не установлен или модель не скачана — wake тихо отключается,
PTT работает как обычно.

Дефолтная фраза "hey jarvis". Альтернативы (через `wake.model`):
- `alexa`
- `computer`
- `hey_mycroft`
- Свой .onnx (укажи абсолютный путь)
```

## 10. Manual Verification Checklist (append to README)

- [ ] `wake.enabled: false` (default): assistant behaves identically to MVP + Piper + ollama
- [ ] `wake.enabled: true`, first run: ~8 MB models download with progress log
- [ ] Second run: TTS available immediately, no download
- [ ] Say "hey jarvis" then "открой блокнот" — notepad opens without pressing PTT
- [ ] 800 ms silence after the command — ASR transcribes and dispatches
- [ ] Command spoken for >10 s — cut off at 10 s, ASR receives the partial
- [ ] PTT continues to work while wake is enabled (hold Ctrl, speak — command runs)
- [ ] Background conversation (no wake phrase) — no false triggers within 1 minute of recording
- [ ] Stop openwakeword model from disk, restart: ERROR log, PTT still works
- [ ] Ctrl+C — wake thread joins within 2 s

## 11. Open Questions / Future Work

- **Custom Russian wake-word** ("эй ассистент") — separate sub-project. Train via openWakeWord's notebook (Synthetic Data API). ~1–3 h.
- **TTS-echo suppression** — pause wake detection while `PiperFeedback._current_stream is not None`. Today the COLLECTING→IDLE reset handles the common case; this is the next improvement.
- **VAD-during-IDLE** — only run wake detection on chunks with speech energy, skip silent ones. Saves ~50 % CPU on always-on systems. Two-stage VAD.
- **Multiple simultaneous wake words** — openWakeWord supports loading several models; pick first to fire. Trivial extension to `WakeWordActivator.__init__`.
- **Sliding threshold** — raise threshold dynamically when many false positives in last N seconds.
- **Continuous attention** — after a successful command, allow 30 s of follow-up commands without wake. Bigger UX feature; defer.

## 12. References

- openWakeWord: https://github.com/dscripka/openWakeWord
- openWakeWord docs: https://github.com/dscripka/openWakeWord/blob/main/README.md
- Pretrained model list: https://github.com/dscripka/openWakeWord/tree/main/openwakeword/resources/models
- MVP design spec: `docs/superpowers/specs/2026-05-19-voice-assistant-design.md`
- Piper TTS spec: `docs/superpowers/specs/2026-05-20-piper-tts-design.md`
- ollama LLM fallback spec: `docs/superpowers/specs/2026-05-20-ollama-fallback-design.md`
