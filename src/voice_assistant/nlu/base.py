from __future__ import annotations
from abc import ABC, abstractmethod
from voice_assistant.core.types import Transcript, Intent


class NLURouter(ABC):
    @abstractmethod
    def route(self, transcript: Transcript) -> Intent:
        ...
