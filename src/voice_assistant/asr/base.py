from __future__ import annotations
from abc import ABC, abstractmethod
from voice_assistant.core.types import AudioSegment, Transcript


class ASREngine(ABC):
    @abstractmethod
    def transcribe(self, segment: AudioSegment) -> Transcript: ...
