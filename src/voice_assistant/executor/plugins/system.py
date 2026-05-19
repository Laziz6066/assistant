from __future__ import annotations
import time
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult

CONFIRM_TIMEOUT_S = 5.0


def register(reg: Registry) -> None:
    pending = {"action": None, "ts": 0.0}

    def _arm(action: str) -> ExecutionResult:
        pending["action"] = action
        pending["ts"] = time.monotonic()
        return ExecutionResult.ok(
            f"awaiting confirm for {action}",
            "Подтвердите: скажите «да»")

    def _current(ctx) -> int:
        getter = getattr(ctx.platform_ops, "get_volume", None)
        return getter() if callable(getter) else 50

    def _clamp(v: int) -> int:
        return max(0, min(100, v))

    def volume_set(slots, ctx) -> ExecutionResult:
        level = int(slots.get("level", 50))
        ctx.platform_ops.set_volume(level)
        return ExecutionResult.ok(f"volume {level}", f"Громкость {level}")

    def volume_up(slots, ctx) -> ExecutionResult:
        ctx.platform_ops.set_volume(_clamp(_current(ctx) + 5))
        return ExecutionResult.ok("volume up", "Громче")

    def volume_down(slots, ctx) -> ExecutionResult:
        ctx.platform_ops.set_volume(_clamp(_current(ctx) - 5))
        return ExecutionResult.ok("volume down", "Тише")

    def lock_screen(slots, ctx) -> ExecutionResult:
        ctx.platform_ops.lock_screen()
        return ExecutionResult.ok("locked", "Заблокировал")

    def shutdown(slots, ctx) -> ExecutionResult:
        return _arm("shutdown")

    def reboot(slots, ctx) -> ExecutionResult:
        return _arm("reboot")

    def confirm_yes(slots, ctx) -> ExecutionResult:
        action = pending["action"]
        if not action:
            return ExecutionResult.ok("nothing to confirm", "Нечего подтверждать")
        if time.monotonic() - pending["ts"] > CONFIRM_TIMEOUT_S:
            pending["action"] = None
            return ExecutionResult.ok("confirm expired", "Время вышло, отмена")
        pending["action"] = None
        ctx.platform_ops.shutdown(reboot=(action == "reboot"))
        return ExecutionResult.ok(f"executing {action}", "Выполняю")

    reg.add("volume_set", volume_set)
    reg.add("volume_up", volume_up)
    reg.add("volume_down", volume_down)
    reg.add("lock_screen", lock_screen)
    reg.add("shutdown", shutdown)
    reg.add("reboot", reboot)
    reg.add("confirm_yes", confirm_yes)
