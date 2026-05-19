from __future__ import annotations
import numpy as np
from loguru import logger
from voice_assistant.core.types import AudioSegment


def _load_silero():
    import torch
    model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
    return model


class VADSegmenter:
    def __init__(self, sample_rate: int, threshold: float,
                 min_speech_ms: int, max_speech_ms: int, model=None):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_ms = min_speech_ms
        self.max_ms = max_speech_ms
        self._model = model

    @property
    def model(self):
        if self._model is None:
            self._model = _load_silero()
        return self._model

    def _has_speech(self, samples: np.ndarray) -> bool:
        import torch
        f32 = samples.astype(np.float32) / 32768.0
        window = 512
        for i in range(0, len(f32) - window, window):
            chunk = torch.from_numpy(f32[i:i + window])
            if float(self.model(chunk, self.sample_rate).item()) >= self.threshold:
                return True
        return False

    def segment(self, samples: np.ndarray) -> AudioSegment | None:
        dur_ms = int(len(samples) * 1000 / self.sample_rate)
        if dur_ms < self.min_ms:
            logger.debug(f"segment {dur_ms}ms below min, discarded")
            return None
        if dur_ms > self.max_ms:
            logger.warning(f"segment {dur_ms}ms exceeds max, trimming")
            samples = samples[: int(self.max_ms * self.sample_rate / 1000)]
        if not self._has_speech(samples):
            logger.debug("no speech detected, discarded")
            return None
        return AudioSegment(samples=samples.astype(np.int16),
                            sample_rate=self.sample_rate)
