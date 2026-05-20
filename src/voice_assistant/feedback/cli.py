from __future__ import annotations
from loguru import logger
from voice_assistant.feedback.base import FeedbackSink


class CLIFeedback(FeedbackSink):
    def _notify(self, message: str) -> None:
        try:
            from plyer import notification
            notification.notify(title="Voice Assistant",
                                message=message, timeout=3)
        except Exception as e:
            logger.debug(f"notification failed: {e}")

    def emit(self, message: str, success: bool = True) -> None:
        prefix = "[OK]" if success else "[!!]"
        print(f"{prefix} {message}", flush=True)
        logger.info(f"feedback: {message} (success={success})")
        self._notify(message)
