from __future__ import annotations
import threading
import numpy as np
from loguru import logger


class RingBuffer:
    def __init__(self, capacity: int):
        self._cap = capacity
        self._buf = np.zeros(0, dtype=np.int16)
        self._lock = threading.Lock()

    def extend(self, chunk: np.ndarray) -> None:
        with self._lock:
            self._buf = np.concatenate([self._buf, chunk])[-self._cap:]

    def snapshot(self) -> np.ndarray:
        with self._lock:
            return self._buf.copy()


class AudioCapture:
    """Continuously records mic into a ring buffer. Thread-based."""

    def __init__(self, sample_rate: int, ring_seconds: float, device: int | None):
        self.sample_rate = sample_rate
        self.device = device
        self.ring = RingBuffer(int(sample_rate * ring_seconds))
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        def _cb(indata, frames, time, status):
            if status:
                logger.warning(f"audio status: {status}")
            self.ring.extend(indata[:, 0].copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate, channels=1, dtype="int16",
                device=self.device, callback=_cb)
            self._stream.start()
        except Exception as e:
            logger.error(f"Cannot open microphone: {e}")
            raise

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
