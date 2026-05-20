from __future__ import annotations
import queue
import threading
from collections.abc import Callable
from pathlib import Path
import numpy as np
from loguru import logger

from voice_assistant.activation.base import Activator
from voice_assistant.activation.models_store import (
    WakeModelStore, WakeModelNotFoundError,
)


_AUDIO_Q_MAXSIZE = 16
_WORKER_GET_TIMEOUT_S = 0.5
_STOP_JOIN_TIMEOUT_S = 2.0
_STOP = object()  # internal sentinel
_LOUDNESS_FLOOR = 200  # int16 peak amplitude that counts as "speech"


class WakeWordActivator(Activator):
    """Always-on wake-word detector.

    State machine:
      IDLE        — feed audio to predict(); transition to COLLECTING when
                    score > threshold
      COLLECTING  — speech is being captured (PTT-equivalent); end on
                    silence (silence_ms) or max ceiling (max_speech_ms)

    Failure policy: any model/setup failure → self._available=False,
    PTT continues working in the surrounding composite.
    """

    def __init__(self, *, model: str, store: WakeModelStore,
                 capture, threshold: float, silence_ms: int,
                 max_speech_ms: int,
                 on_state_change: Callable[[bool], None],
                 _sample_rate: int = 16000) -> None:
        self._model_name = model
        self._store = store
        self._capture = capture
        self._threshold = threshold
        self._silence_ms = silence_ms
        self._max_speech_ms = max_speech_ms
        self._on_state_change = on_state_change
        self._sample_rate = _sample_rate

        self._audio_q: queue.Queue = queue.Queue(maxsize=_AUDIO_Q_MAXSIZE)
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._available = False
        self._state = "IDLE"
        self._onnx_path: Path | None = None

    # ---- lifecycle ----

    def start(self) -> None:
        try:
            self._onnx_path = self._store.ensure(self._model_name)
        except WakeModelNotFoundError as e:
            logger.error(f"wake disabled — model unavailable: {e}")
            self._available = False
            return
        except Exception as e:
            logger.error(f"wake disabled — unexpected store error: {e}")
            self._available = False
            return
        try:
            self._load_engine(self._onnx_path)
        except Exception as e:
            logger.error(f"wake disabled — engine load failed: {e}")
            self._available = False
            return
        self._capture.subscribe(self._on_audio_chunk)
        self._available = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True,
            name="WakeWordActivator._worker")
        self._thread.start()
        logger.info(f"wake-word armed: {self._model_name!r} "
                    f"(threshold={self._threshold})")

    def stop(self) -> None:
        if self._available:
            try:
                self._capture.unsubscribe(self._on_audio_chunk)
            except Exception:
                logger.exception("wake unsubscribe failed")
        self._stop_evt.set()
        try:
            self._audio_q.put_nowait(_STOP)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=_STOP_JOIN_TIMEOUT_S)

    # ---- pub/sub callback (sounddevice thread; must be fast) ----

    def _on_audio_chunk(self, chunk: np.ndarray) -> None:
        try:
            self._audio_q.put_nowait(chunk)
        except queue.Full:
            logger.debug("wake _audio_q full, dropping chunk")

    # ---- worker thread + state machine ----

    def _worker(self) -> None:
        collecting_ms = 0
        silence_ms = 0
        while not self._stop_evt.is_set():
            try:
                item = self._audio_q.get(timeout=_WORKER_GET_TIMEOUT_S)
            except queue.Empty:
                continue
            if item is _STOP:
                break
            chunk_ms = int(1000 * len(item) / self._sample_rate)
            try:
                score = self._predict_score(item)
            except Exception:
                logger.exception("wake predict failed")
                continue
            if self._state == "IDLE":
                if score >= self._threshold:
                    logger.info(f"wake detected (score={score:.2f})")
                    self._state = "COLLECTING"
                    collecting_ms = 0
                    silence_ms = 0
                    self._on_state_change(True)
            else:  # COLLECTING
                collecting_ms += chunk_ms
                if score >= self._threshold:
                    silence_ms = 0
                else:
                    silence_ms += chunk_ms
                if (silence_ms >= self._silence_ms
                        or collecting_ms >= self._max_speech_ms):
                    self._state = "IDLE"
                    try:
                        self._reset_engine()
                    except Exception:
                        logger.exception("wake reset_engine failed")
                    self._on_state_change(False)

    # ---- seams overridable by tests; real impl in Task 7 ----

    def _load_engine(self, onnx_path: Path) -> None:
        """Load the openWakeWord model. Default: no-op (overridden in Task 7)."""

    def _predict_score(self, chunk: np.ndarray) -> float:
        """Return the wake-word score for this chunk. Tests stub this."""
        return 0.0

    def _reset_engine(self) -> None:
        """Reset prediction buffer to avoid re-trigger. Tests stub this."""

    # ---- helpers ----

    @staticmethod
    def _is_loud(chunk: np.ndarray) -> bool:
        return bool(np.max(np.abs(chunk)) >= _LOUDNESS_FLOOR)
