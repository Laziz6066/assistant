from __future__ import annotations
from collections.abc import Sequence
from loguru import logger

from voice_assistant.feedback.base import FeedbackSink


class CompositeFeedback(FeedbackSink):
    """Fan-out FeedbackSink. Calls every child sink for emit/cancel/start/stop.
    An exception from one child is logged and does not prevent later children
    from being called.
    """

    def __init__(self, sinks: Sequence[FeedbackSink]) -> None:
        self._sinks: list[FeedbackSink] = list(sinks)

    def emit(self, message: str, success: bool = True) -> None:
        for sink in self._sinks:
            try:
                sink.emit(message, success)
            except Exception:
                logger.exception(f"sink {type(sink).__name__} emit failed")

    def cancel(self) -> None:
        for sink in self._sinks:
            try:
                sink.cancel()
            except Exception:
                logger.exception(f"sink {type(sink).__name__} cancel failed")

    def start(self) -> None:
        for sink in self._sinks:
            try:
                sink.start()
            except Exception:
                logger.exception(f"sink {type(sink).__name__} start failed")

    def stop(self) -> None:
        for sink in self._sinks:
            try:
                sink.stop()
            except Exception:
                logger.exception(f"sink {type(sink).__name__} stop failed")
