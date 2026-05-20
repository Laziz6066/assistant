from __future__ import annotations
from abc import ABC, abstractmethod


class FeedbackSink(ABC):
    @abstractmethod
    def emit(self, message: str, success: bool = True) -> None: ...
