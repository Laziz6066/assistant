from __future__ import annotations
import sys
from loguru import logger


def setup_logging(level: str = "INFO", logfile: str | None = "voice_assistant.log"):
    logger.remove()
    logger.add(sys.stderr, level=level, enqueue=True)
    if logfile:
        logger.add(logfile, level=level, rotation="10 MB", enqueue=True)
    return logger
