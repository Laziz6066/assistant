from __future__ import annotations
import threading
from collections.abc import Callable
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
    """Continuously records mic into a ring buffer.

    Subscribers (via subscribe()) receive each new audio chunk as a 1-D
    int16 numpy array. Subscriber callbacks are invoked from the
    sounddevice callback thread and MUST return in <5ms — otherwise frames
    are dropped. Heavy work belongs in a worker thread fed by a queue.
    """

    def __init__(self, sample_rate: int, ring_seconds: float, device: int | None):
        self.sample_rate = sample_rate
        self.device = device
        self.ring = RingBuffer(int(sample_rate * ring_seconds))
        self._stream = None
        self._subscribers: list[Callable[[np.ndarray], None]] = []
        self._sub_lock = threading.Lock()

    def subscribe(self, cb: Callable[[np.ndarray], None]) -> None:
        with self._sub_lock:
            self._subscribers.append(cb)

    def unsubscribe(self, cb: Callable[[np.ndarray], None]) -> None:
        with self._sub_lock:
            if cb in self._subscribers:
                self._subscribers.remove(cb)

    def _dispatch(self, indata, frames, time, status) -> None:
        """Internal: route a sounddevice chunk into the ring + subscribers.

        Extracted as a method so unit tests can drive it directly without
        a real audio device.
        """
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

    def start(self) -> None:
        import sounddevice as sd

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate, channels=1, dtype="int16",
                device=self.device, callback=self._dispatch)
            self._stream.start()
        except Exception as e:
            logger.error(f"Cannot open microphone: {e}")
            raise

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
