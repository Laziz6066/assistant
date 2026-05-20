from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig


def test_context_exposes_config_and_platform():
    ctx = ExecutorContext(config=AppConfig(), platform_ops=object())
    assert ctx.config is not None
    assert ctx.platform_ops is not None


def test_resolve_app_alias():
    cfg = AppConfig(app_aliases={"телега": "telegram"})
    ctx = ExecutorContext(config=cfg, platform_ops=object())
    assert ctx.resolve_app("телега") == "telegram"
    assert ctx.resolve_app("notepad") == "notepad"


def test_executor_context_defaults_mode_store_to_none():
    from voice_assistant.executor.context import ExecutorContext
    from voice_assistant.config import AppConfig
    from unittest.mock import MagicMock

    ctx = ExecutorContext(config=AppConfig(), platform_ops=MagicMock())
    assert ctx.mode_store is None


def test_executor_context_accepts_mode_store():
    from voice_assistant.executor.context import ExecutorContext
    from voice_assistant.config import AppConfig
    from voice_assistant.dictation.mode_store import ModeStore
    from unittest.mock import MagicMock

    store = ModeStore()
    ctx = ExecutorContext(config=AppConfig(), platform_ops=MagicMock(),
                            mode_store=store)
    assert ctx.mode_store is store
