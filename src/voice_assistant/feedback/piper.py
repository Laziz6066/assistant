from __future__ import annotations
import queue
import threading
from pathlib import Path
from loguru import logger

from voice_assistant.feedback.base import FeedbackSink
from voice_assistant.feedback.voice_models import (
    VoiceModelStore, VoiceDownloadError,
)

_QUEUE_MAXSIZE = 8
_WORKER_GET_TIMEOUT_S = 0.5
_STOP_JOIN_TIMEOUT_S = 2.0
_STOP = object()  # sentinel; not shared with pipeline STOP


class PiperFeedback(FeedbackSink):
    """Plays TTS for assistant responses on a background thread.

    Lifecycle:
      __init__()  → object only; no model load, no thread.
      start()     → load voice model, spawn worker. _available=True on success.
      emit(msg)   → enqueue message; non-blocking; returns in <1ms.
      cancel()    → drain queue + abort current playback.
      stop()      → put STOP sentinel + join worker.

    Failure policy: any model/audio failure → self._available=False, log once,
    silent thereafter. Never raises into the caller.
    """

    def __init__(self, voice: str, store: VoiceModelStore,
                 length_scale: float = 1.0) -> None:
        self._voice_name = voice
        self._store = store
        self._length_scale = length_scale

        self._tts_q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()
        self._current_stream = None  # set inside _synthesize_and_play
        self._thread: threading.Thread | None = None
        self._available = False
        self._unavailable_warned = False
        self._voice_paths: tuple[Path, Path] | None = None

    def start(self) -> None:
        try:
            self._voice_paths = self._store.ensure(self._voice_name)
        except VoiceDownloadError as e:
            logger.error(f"TTS disabled — voice model unavailable: {e}")
            self._available = False
            return
        except Exception as e:
            logger.error(f"TTS disabled — unexpected error preparing voice: {e}")
            self._available = False
            return

        try:
            self._load_engine(*self._voice_paths)
        except Exception as e:
            logger.error(f"TTS disabled — engine load failed: {e}")
            self._available = False
            return

        self._available = True
        self._thread = threading.Thread(target=self._worker, daemon=True,
                                         name="PiperFeedback._worker")
        self._thread.start()

    def emit(self, message: str, success: bool = True) -> None:
        if not self._available:
            if not self._unavailable_warned:
                logger.warning("TTS unavailable, suppressing further audio")
                self._unavailable_warned = True
            return
        try:
            self._tts_q.put_nowait(message)
        except queue.Full:
            logger.warning(f"TTS queue full, dropping: {message!r}")

    def cancel(self) -> None:
        # Drain pending queue
        drained = 0
        while True:
            try:
                self._tts_q.get_nowait()
                drained += 1
            except queue.Empty:
                break
        # Abort active playback
        with self._lock:
            stream = self._current_stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
        if drained:
            logger.debug(f"TTS cancel dropped {drained} pending message(s)")

    def stop(self) -> None:
        self._stop_evt.set()
        try:
            self._tts_q.put_nowait(_STOP)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=_STOP_JOIN_TIMEOUT_S)

    def _worker(self) -> None:
        while not self._stop_evt.is_set():
            try:
                msg = self._tts_q.get(timeout=_WORKER_GET_TIMEOUT_S)
            except queue.Empty:
                continue
            if msg is _STOP:
                break
            try:
                self._synthesize_and_play(msg)
            except Exception:
                logger.exception(f"TTS playback failed for {msg!r}")

    # --- Seams overridable by tests; real implementation lives in Task 6 ---

    def _load_engine(self, onnx_path: Path, json_path: Path) -> None:
        """Load the Piper voice model. Default: no-op (overridden in Task 6)."""
        pass

    def _synthesize_and_play(self, message: str) -> None:
        """Synthesize `message` and play it. Default raises NotImplementedError
        — Task 6 supplies the real implementation, tests subclass to stub."""
        raise NotImplementedError("subclass or Task 6 must implement")
