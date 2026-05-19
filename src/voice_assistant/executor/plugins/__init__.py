from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import apps, windows, browser, files, clipboard


def register_all() -> None:
    reg = global_registry()
    apps.register(reg)
    windows.register(reg)
    browser.register(reg)
    files.register(reg)
    clipboard.register(reg)
