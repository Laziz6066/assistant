from __future__ import annotations
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def _press(*keys: str) -> None:
    import pyautogui
    pyautogui.hotkey(*keys)


def register(reg: Registry) -> None:
    def minimize_all(slots, ctx) -> ExecutionResult:
        _press("win", "d")
        return ExecutionResult.ok("minimized all", "Свернул всё")

    def close_window(slots, ctx) -> ExecutionResult:
        _press("alt", "f4")
        return ExecutionResult.ok("closed window", "Закрыл окно")

    def switch_window(slots, ctx) -> ExecutionResult:
        _press("alt", "tab")
        return ExecutionResult.ok("switched window", "Переключил")

    reg.add("minimize_all", minimize_all)
    reg.add("close_window", close_window)
    reg.add("switch_window", switch_window)
