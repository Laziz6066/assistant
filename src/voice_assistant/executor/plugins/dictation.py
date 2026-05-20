from __future__ import annotations
from voice_assistant.core.types import ExecutionResult
from voice_assistant.executor.registry import Registry


def _start_dictation(slots: dict, ctx) -> ExecutionResult:
    if ctx.mode_store is None:
        return ExecutionResult.fail("Режим диктовки выключен")
    ctx.mode_store.start_dictation()
    return ExecutionResult.ok("Режим диктовки", tts_response="Режим диктовки")


def _stop_dictation(slots: dict, ctx) -> ExecutionResult:
    if ctx.mode_store is not None:
        ctx.mode_store.stop_dictation()
    return ExecutionResult.ok("ok", tts_response="Готово")


def register(reg: Registry) -> None:
    reg.add("start_dictation", _start_dictation)
    reg.add("stop_dictation", _stop_dictation)
