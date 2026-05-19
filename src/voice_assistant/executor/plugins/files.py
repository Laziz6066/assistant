from __future__ import annotations
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def register(reg: Registry) -> None:
    def open_path(slots, ctx) -> ExecutionResult:
        name = slots.get("name", "").strip()
        if not name:
            return ExecutionResult.fail("no path", "Что открыть?")
        target = ctx.resolve_path(name)
        ctx.platform_ops.open_path(target)
        return ExecutionResult.ok(f"opened {target}", f"Открыл {name}")

    reg.add("open_path", open_path)
