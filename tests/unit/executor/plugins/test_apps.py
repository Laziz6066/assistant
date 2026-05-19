from unittest.mock import MagicMock
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.apps as apps


def _ctx():
    return ExecutorContext(config=AppConfig(app_aliases={"телега": "telegram"}),
                           platform_ops=MagicMock())


def test_open_app_resolves_alias_and_launches():
    reg = Registry()
    apps.register(reg)
    ctx = _ctx()
    res = reg.dispatch(Intent("open_app", {"app": "телега"}), ctx)
    ctx.platform_ops.launch_app.assert_called_once_with("telegram")
    assert res.success


def test_close_app_calls_platform():
    reg = Registry()
    apps.register(reg)
    ctx = _ctx()
    res = reg.dispatch(Intent("close_app", {"app": "telegram"}), ctx)
    ctx.platform_ops.close_app.assert_called_once_with("telegram")
    assert res.success


def test_open_app_rejects_shell_metacharacters():
    reg = Registry()
    apps.register(reg)
    ctx = _ctx()
    res = reg.dispatch(Intent("open_app", {"app": "foo & del x"}), ctx)
    ctx.platform_ops.launch_app.assert_not_called()
    assert res.success is False
