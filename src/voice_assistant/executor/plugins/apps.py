from __future__ import annotations
import re
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult

# Security: the executor is the boundary between voice-transcribed text and the
# OS. platform_ops._spawn uses shell=True, so reject any resolved target that
# contains shell metacharacters before it can reach a shell.
_UNSAFE = re.compile(r"[&|;<>`$\n\r%]")


def _is_safe(target: str) -> bool:
    return bool(target) and _UNSAFE.search(target) is None


def register(reg: Registry) -> None:
    def open_app(slots, ctx) -> ExecutionResult:
        target = ctx.resolve_app(slots.get("app", ""))
        if not target:
            return ExecutionResult.fail("no app given", "Какое приложение?")
        if not _is_safe(target):
            return ExecutionResult.fail(
                f"unsafe app name rejected: {target!r}",
                "Не могу открыть это приложение")
        ctx.platform_ops.launch_app(target)
        return ExecutionResult.ok(f"launched {target}", f"Открыл {target}")

    def close_app(slots, ctx) -> ExecutionResult:
        target = ctx.resolve_app(slots.get("app", ""))
        if not target:
            return ExecutionResult.fail("no app given", "Какое приложение?")
        if not _is_safe(target):
            return ExecutionResult.fail(
                f"unsafe app name rejected: {target!r}",
                "Не могу закрыть это приложение")
        ctx.platform_ops.close_app(target)
        return ExecutionResult.ok(f"closed {target}", f"Закрыл {target}")

    reg.add("open_app", open_app)
    reg.add("close_app", close_app)
