from __future__ import annotations
from typing import Callable
from loguru import logger
from voice_assistant.core.types import Intent, ExecutionResult

Handler = Callable[[dict, object], ExecutionResult]


class Registry:
    def __init__(self):
        self._handlers: dict[str, Handler] = {}

    def add(self, name: str, fn: Handler) -> None:
        self._handlers[name] = fn

    def dispatch(self, intent: Intent, ctx: object) -> ExecutionResult:
        fn = self._handlers.get(intent.name)
        if fn is None:
            return ExecutionResult.fail(
                f"unknown intent: {intent.name}",
                tts_response="Не понял, повтори")
        try:
            return fn(intent.slots, ctx)
        except Exception as e:  # contained: pipeline must survive
            logger.exception(f"plugin {intent.name} failed")
            return ExecutionResult.fail(f"plugin error: {e}",
                                        tts_response="Ошибка выполнения")


_GLOBAL = Registry()


def register_intent(name: str, registry: Registry | None = None):
    target = registry or _GLOBAL

    def deco(fn: Handler) -> Handler:
        target.add(name, fn)
        return fn

    return deco


def global_registry() -> Registry:
    return _GLOBAL
