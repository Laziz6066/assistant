from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass(frozen=True)
class AudioSegment:
    samples: np.ndarray  # int16 mono
    sample_rate: int

    @property
    def duration_ms(self) -> int:
        return int(len(self.samples) * 1000 / self.sample_rate)


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    confidence: float
    duration_ms: int


@dataclass(frozen=True)
class Intent:
    name: str
    slots: dict = field(default_factory=dict)
    confidence: float = 1.0

    @classmethod
    def unknown(cls) -> "Intent":
        return cls(name="unknown", slots={}, confidence=0.0)


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    message: str
    tts_response: str = ""

    @classmethod
    def ok(cls, message: str, tts_response: str = "") -> "ExecutionResult":
        return cls(success=True, message=message, tts_response=tts_response or message)

    @classmethod
    def fail(cls, message: str, tts_response: str = "") -> "ExecutionResult":
        return cls(success=False, message=message, tts_response=tts_response or message)
