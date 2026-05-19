from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import apps


def register_all() -> None:
    reg = global_registry()
    apps.register(reg)
