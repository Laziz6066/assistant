from __future__ import annotations
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def _press(*keys: str) -> None:
    import pyautogui
    pyautogui.hotkey(*keys)


def _read_clipboard() -> str:
    import ctypes
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard(0)
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        text = ctypes.c_wchar_p(ptr).value or ""
        kernel32.GlobalUnlock(handle)
        return text
    finally:
        user32.CloseClipboard()


def register(reg: Registry) -> None:
    def copy(slots, ctx) -> ExecutionResult:
        _press("ctrl", "c")
        return ExecutionResult.ok("copied", "Скопировал")

    def paste(slots, ctx) -> ExecutionResult:
        _press("ctrl", "v")
        return ExecutionResult.ok("pasted", "Вставил")

    def read(slots, ctx) -> ExecutionResult:
        text = _read_clipboard()
        if not text:
            return ExecutionResult.ok("clipboard empty", "Буфер пуст")
        snippet = text[:200]
        return ExecutionResult.ok(f"clipboard: {snippet}",
                                  f"В буфере: {snippet}")

    reg.add("clipboard_copy", copy)
    reg.add("clipboard_paste", paste)
    reg.add("clipboard_read", read)
