from __future__ import annotations
from abc import ABC, abstractmethod


class FeedbackSink(ABC):
    @abstractmethod
    def emit(self, message: str, success: bool = True) -> None: ...

    def start(self) -> None:
        """Optional: bring up resources (threads, models). Default no-op."""

    def cancel(self) -> None:
        """Optional: cancel any in-flight output. Default no-op."""

    def stop(self) -> None:
        """Optional: tear down resources. Default no-op."""
