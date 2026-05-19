from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import (
    apps, windows, browser, files, clipboard, system,
)


def register_all() -> None:
    reg = global_registry()
    for mod in (apps, windows, browser, files, clipboard, system):
        mod.register(reg)
