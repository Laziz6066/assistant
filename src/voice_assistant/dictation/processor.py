from __future__ import annotations
from loguru import logger

from voice_assistant.dictation.punctuation import normalize_punctuation


class DictationProcessor:
    """Normalizes punctuation and types the result via platform_ops.

    Failure policy: any exception raised by platform_ops.type_text is
    logged and swallowed — the pipeline never observes typing failures.
    """

    def __init__(self, platform_ops) -> None:
        self._ops = platform_ops

    def type_transcript(self, transcript_text: str) -> None:
        normalized = normalize_punctuation(transcript_text)
        if not normalized:
            return
        try:
            self._ops.type_text(normalized)
        except Exception:
            logger.exception(
                f"dictation type_text failed for {len(normalized)} chars")
