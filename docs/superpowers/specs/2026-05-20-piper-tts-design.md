# Piper TTS — Design Spec

**Date:** 2026-05-20
**Status:** Approved, ready for implementation plan
**Sub-project:** Beta (post-MVP)
**Depends on:** voice-assistant MVP (commit `230ed00` or later on branch `worktree-voice-assistant-mvp`)

## 1. Goal

Add neural TTS so the assistant speaks responses out loud instead of only printing them.
Closes the feedback loop: user can use the assistant without watching the screen.

## 2. Scope

**In:**
- Russian voice synthesis via Piper (`ru_RU-irina-medium` default)
- Asynchronous playback with interruption on next PTT-down
- Lazy download of voice model on first run (HuggingFace)
- Graceful degradation: TTS failure never breaks the pipeline
- New `FeedbackSink` implementations: `PiperFeedback`, `CompositeFeedback`

**Out (deferred):**
- Voice picker UI / runtime voice switching
- Streaming synthesis
- TTS audio mixing with system sounds
- Checksum verification of downloaded models
- Mirror fallback when HuggingFace unreachable
- Real-time progress bar (only log every 10 MB)
- Multi-voice management (`store.list_available()`)
- Speaking only some messages (v1: speak every `feedback.emit` call)

## 3. Decisions

| Question | Decision |
|---|---|
| Replace or supplement CLI feedback | Supplement — CLI + Piper run in parallel via `CompositeFeedback` |
| Playback synchrony | Async with interruption (Siri-like) |
| Voice model distribution | Lazy download from HuggingFace on first run |
| Default voice | `ru_RU-irina-medium` |
| Voice storage location | `~/.voice-assistant/voices/` (user dir, override via `cfg.tts.voices_dir`) |
| Interruption trigger | PTT key DOWN cancels current playback and clears queue |
| TTS failure policy | Set `self._available = False`, log once, continue text-only |
| TTS queue overflow policy | Drop new messages with warning log (don't block pipeline) |

## 4. Architecture

### 4.1 New files

```
src/voice_assistant/feedback/
  piper.py          # PiperFeedback(FeedbackSink) — TTS worker thread
  composite.py      # CompositeFeedback(FeedbackSink) — fan-out
  voice_models.py   # VoiceModelStore — find/download/cache .onnx files
```

### 4.2 Modified files

```
src/voice_assistant/feedback/base.py
  + FeedbackSink.cancel() — optional, default no-op

src/voice_assistant/config.py
  + class TTSConfig(BaseModel):
      enabled: bool = True
      voice: str = "ru_RU-irina-medium"
      voices_dir: Path = Path.home() / ".voice-assistant" / "voices"
      length_scale: float = 1.0
  + AppConfig.tts: TTSConfig = TTSConfig()

src/voice_assistant/main.py
  - _build(): build CompositeFeedback([CLIFeedback(), PiperFeedback(...)])
    if cfg.tts.enabled else CLIFeedback() alone
  - on_state_change(held=True): also call feedback.cancel()
  - main(): call feedback.stop() before capture.stop()
  - _shutdown: best-effort feedback.cancel() so a long playback doesn't
    delay shutdown

pyproject.toml
  + piper-tts>=1.2
  + requests>=2.28
```

### 4.3 Data flow

```
Pipeline.process_segment (worker thread)
  result = registry.dispatch(intent, ctx)
  feedback.emit(result.tts_response, success=result.success)
                │
                ▼
CompositeFeedback.emit(msg, success)
  for sink in self._sinks:
    try: sink.emit(msg, success)
    except: logger.exception; continue   # one bad sink doesn't kill others
       │
       ├── CLIFeedback.emit() — synchronous (print + plyer)
       └── PiperFeedback.emit() — tts_q.put_nowait(msg), returns < 1ms
                                                  │
                                                  ▼
                  PiperFeedback._worker (daemon thread)
                    while not stop_evt.is_set():
                      try: msg = tts_q.get(timeout=0.5)
                      except queue.Empty: continue
                      if msg is STOP: break
                      try:
                        wav = piper.synthesize(msg)   # CPU 50-200ms
                        with sd.OutputStream(...) as out:
                          self._current_stream = out
                          out.write(wav)               # blocking play
                      except CancelledError: continue
                      except Exception: logger.exception; continue
                      finally: self._current_stream = None
```

### 4.4 Threading & synchronization

- `tts_q: queue.Queue[str | object]` with `maxsize=8`. `STOP` sentinel singleton (separate from the pipeline's STOP — TTS owns its own).
- `_current_stream: sd.OutputStream | None` guarded by `self._lock: threading.Lock`.
- `stop_evt: threading.Event` shared between `_worker` and `cancel()/stop()`.
- `feedback.emit()` always returns in <1ms: CLI prints synchronously, Piper only puts into queue. The Pipeline worker thread is never blocked by TTS synthesis or playback.
- Queue overflow: `tts_q.put_nowait()` raises `queue.Full` → catch in `PiperFeedback.emit()`, log warning, drop message. Pipeline keeps moving.

### 4.5 Interruption (`cancel()`)

```python
def cancel(self) -> None:
    # 1. Drain pending queue
    while True:
        try: self._tts_q.get_nowait()
        except queue.Empty: break
    # 2. Stop current playback (if any)
    with self._lock:
        if self._current_stream is not None:
            try: self._current_stream.abort()
            except Exception: pass
```

`_worker` either catches the `PortAudioError` from the aborted stream or finishes the current `out.write()` early — then loops back to `get()`.

Hooked up from `main._build()`:
```python
def on_state_change(held: bool) -> None:
    nonlocal mark
    if held:
        feedback.cancel()         # ← NEW: PTT down kills any in-flight TTS
        mark = len(capture.ring.snapshot())
    else:
        raw = capture.ring.snapshot()[mark:]
        qs.speech_q.put(raw)
```

### 4.6 Lifecycle

| Stage | Action |
|---|---|
| `PiperFeedback.__init__(cfg, store)` | Build the object. NO model load, NO thread start. Fast. |
| `PiperFeedback.start()` | Lazy-resolve voice via `store.ensure(voice)`. Load Piper. Spawn `_worker`. Set `self._available = True` on success, `False` on exception. |
| `PiperFeedback.emit(msg, success)` | If `_available`: `tts_q.put_nowait(msg)`. Else: silent skip (with one-time log). |
| `PiperFeedback.cancel()` | Drain queue + abort stream. Safe to call from any thread. |
| `PiperFeedback.stop()` | Set `stop_evt`, put `STOP` in queue, join thread (timeout=2s). |

Wired into `main()`:
```python
def main() -> int:
    ...
    pipe, qs, capture, ptt, vad, feedback = _build(...)   # tuple grows
    try:
        capture.start()
    except Exception as e:
        logger.error(f"microphone unavailable: {e}")
        return 1
    feedback.start()      # ← starts CLI (no-op) + Piper (loads model + thread)
    ...
    worker.join()
    feedback.stop()       # ← stops TTS thread
    ptt.stop()
    capture.stop()
```

`CompositeFeedback.start()/stop()/cancel()` fan out to children.

## 5. Voice Model Distribution

### 5.1 Storage

```
~/.voice-assistant/voices/
  ru_RU-irina-medium.onnx        # ~63 MB
  ru_RU-irina-medium.onnx.json   # ~1 KB
  .tmp/                          # partial downloads, cleaned on start
```

### 5.2 Source

HuggingFace `rhasspy/piper-voices`:
```
https://huggingface.co/rhasspy/piper-voices/resolve/main/<lang>/<lang_country>/<speaker>/<quality>/<filename>
```

For `ru_RU-irina-medium`:
- `.../ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx`
- `.../ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json`

The URL parsing of `<voice_name> → (lang, lang_country, speaker, quality)` lives in `VoiceModelStore._url_for(voice_name)`. Parses `ru_RU-irina-medium` into `("ru", "ru_RU", "irina", "medium")`.

### 5.3 Interface

```python
class VoiceModelStore:
    def __init__(self, voices_dir: Path): ...

    def ensure(self, voice_name: str) -> tuple[Path, Path]:
        """Return (onnx_path, json_path). Download if missing.
        Raises VoiceDownloadError on network/disk/404 failure."""

    def is_present(self, voice_name: str) -> bool:
        """True if both files exist and .onnx > 1 MB."""
```

### 5.4 Download flow

1. `ensure(voice)` checks `is_present()` → if True, return paths immediately.
2. Otherwise: log `"Downloading voice model {voice} (~63 MB)..."`.
3. `requests.get(url, stream=True, timeout=30)` for `.onnx` to `.tmp/{voice}.onnx.part`. Log progress every 10 MB.
4. On 200 OK + complete: `os.replace(.tmp/X.part, voices_dir/X)` — atomic.
5. Repeat for `.onnx.json`.
6. On any failure: clean `.tmp/` for this voice, raise `VoiceDownloadError(reason)`.

### 5.5 Cleanup

`VoiceModelStore.__init__` removes any files in `voices_dir/.tmp/` older than the current process invocation (or all files in `.tmp/` unconditionally — simpler, safer).

## 6. Error Handling

| Layer | Error | Behaviour |
|---|---|---|
| `VoiceModelStore.ensure()` | Network unreachable | `VoiceDownloadError("network unreachable")` |
| `VoiceModelStore.ensure()` | Disk full | `VoiceDownloadError("disk write failed: {e}")` |
| `VoiceModelStore.ensure()` | HTTP 404 | `VoiceDownloadError("voice {name} not found at {url}")` |
| `VoiceModelStore.ensure()` | Partial download (connection drop) | Same as above; `.tmp/` cleaned next start |
| `PiperFeedback.start()` | `VoiceDownloadError` | `self._available = False`, log ERROR with reason. No raise — graceful degrade. |
| `PiperFeedback.start()` | Piper model load fails (corrupt ONNX) | Same as above. |
| `PiperFeedback.start()` | sounddevice fails to query output device | Same as above. |
| `PiperFeedback.emit()` | `_available is False` | One-time WARNING ("TTS unavailable"), then silent. Never raises. |
| `PiperFeedback.emit()` | `tts_q.put_nowait` → `queue.Full` | WARNING ("TTS queue full, dropping"), return. |
| `PiperFeedback._worker` | `piper.synthesize` raises | `logger.exception`, continue loop. Worker survives. |
| `PiperFeedback._worker` | `sd.OutputStream` raises | `logger.exception`, set `_available = False`, exit loop (no device → no point). |
| `PiperFeedback._worker` | Cancelled via `cancel()` | Caught as `PortAudioError` or just early-completes `write()`. Continue. |
| `CompositeFeedback.emit/cancel/start/stop` | A child sink raises | `logger.exception`, continue to next sink. |

**Invariant:** No TTS-side exception ever propagates to the Pipeline thread. CLIFeedback keeps printing always.

## 7. Configuration

```yaml
# config/default.yaml
tts:
  enabled: true
  voice: ru_RU-irina-medium
  voices_dir: ~/.voice-assistant/voices       # ~ expanded by TTSConfig validator
  length_scale: 1.0                           # 0.8 = faster, 1.2 = slower
```

Pydantic v2 does NOT expand `~` automatically. `TTSConfig` declares `voices_dir: Path` plus a `@field_validator("voices_dir")` that calls `Path(value).expanduser()` so both `~/...` and absolute paths work.

`TTSConfig.enabled = false` disables Piper entirely — `_build()` constructs only `CLIFeedback()`. No Piper import or model load happens.

## 8. Testing Strategy

### 8.1 Mocks

- `piper.PiperVoice` — mocked, `synthesize()` returns a pre-made `numpy.ndarray` of int16
- `sounddevice.OutputStream` — mocked context manager, records `.write()` calls
- `requests.get` — mocked for `VoiceModelStore` tests
- Real `queue.Queue` and real `threading` — synchronization is part of what we test

### 8.2 Unit tests (≥80% coverage target)

`tests/unit/feedback/test_composite.py`:
- `emit()` fans out to all sinks in order
- One sink raising doesn't prevent later sinks from being called
- `cancel()` fans out (every sink that has `cancel` gets it)
- `start()`/`stop()` fan out

`tests/unit/feedback/test_piper.py`:
- `emit()` enqueues without blocking; verify under 1ms latency
- `cancel()` drains queue and aborts current stream (when there is one)
- `_worker` processes multiple messages in FIFO order
- `_worker` survives `synthesize` exception
- `_worker` exits cleanly on STOP sentinel
- `_available=False` → `emit()` is silent (no queue operations)
- `start()` with `VoiceDownloadError` from store → `_available=False`, no thread, no raise
- Queue overflow → warning log, message dropped, pipeline-side unaffected

`tests/unit/feedback/test_voice_models.py`:
- `is_present()` truth table: both files present + size OK / one missing / size too small
- `ensure()` skips download when present
- `ensure()` downloads atomically (mock 200 OK)
- `ensure()` cleans `.tmp/` on partial failure (mock connection drop mid-stream)
- `ensure()` raises `VoiceDownloadError` on 404 / network error / disk write failure
- `__init__` cleans stale `.tmp/` files on start
- `_url_for("ru_RU-irina-medium")` → expected HF URL parts

### 8.3 Integration test (optional)

`tests/integration/test_piper_real.py` with `@pytest.mark.requires_voice_model`:
- If `~/.voice-assistant/voices/ru_RU-irina-medium.onnx` exists, do one real synth + verify .wav output
- Skip otherwise; not in default suite

### 8.4 What we don't test

- Real audio playback (sounddevice mocked)
- Real HTTP download (requests mocked)
- Piper itself (upstream's concern)

## 9. Manual Verification Checklist

Add to `README.md` under existing checklist:

- [ ] First run: voice model downloads (~30 s) with progress log every 10 MB
- [ ] Second run: TTS available immediately (no download)
- [ ] "открой блокнот" → notepad launches AND voice says "Открыл блокнот"
- [ ] Long response ("прочитай буфер" on a long clipboard) → press PTT mid-playback → audio cuts off cleanly
- [ ] Ctrl+C during TTS playback → shuts down within 2 s
- [ ] Disconnect network, delete voice from `~/.voice-assistant/voices/` → assistant starts text-only with ERROR log
- [ ] Set `tts.enabled: false` → no Piper import, normal text-only operation

## 10. Open Questions / Future Work

- **Volume control via voice ("тише говори")** — would need TTS volume knob in config, exposed by a new system plugin intent. Out of scope for this spec.
- **Voice picker plugin** — `"включи другой голос ирина|руслан|денис"` — needs `VoiceModelStore.list_available()` + runtime engine swap. Beta-2.
- **Streaming synthesis** — Piper streams phonemes → audio chunks; could reduce first-syllable latency from ~200ms to ~50ms. Not measured yet; defer until benchmarking shows it matters.
- **Caching synth output for canned phrases** — "Не понял, повтори" is said often; caching its WAV would save ~150ms. Tiny gain, defer.

## 11. References

- Piper: https://github.com/rhasspy/piper
- Piper voices: https://huggingface.co/rhasspy/piper-voices
- MVP design spec: `docs/superpowers/specs/2026-05-19-voice-assistant-design.md`
- MVP implementation plan: `docs/superpowers/plans/2026-05-19-voice-assistant-mvp.md`
