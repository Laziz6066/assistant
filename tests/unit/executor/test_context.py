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
