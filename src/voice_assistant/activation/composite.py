from __future__ import annotations
from collections.abc import Sequence
from loguru import logger

from voice_assistant.activation.base import Activator


class CompositeActivator(Activator):
    """Fan-out Activator. start()/stop() are called on every child in order.
    A child raising does not prevent later children from being called.
    """

    def __init__(self, activators: Sequence[Activator]) -> None:
        self._activators = list(activators)

    def start(self) -> None:
        for a in self._activators:
            try:
                a.start()
            except Exception:
                logger.exception(
                    f"activator {type(a).__name__} start failed")

    def stop(self) -> None:
        for a in self._activators:
            try:
                a.stop()
            except Exception:
                logger.exception(
                    f"activator {type(a).__name__} stop failed")
