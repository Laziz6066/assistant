from unittest.mock import MagicMock
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.files as files


def test_open_path_resolves_alias_and_calls_platform():
    reg = Registry()
    files.register(reg)
    cfg = AppConfig(path_aliases={"загрузки": "~/Downloads"})
    ctx = ExecutorContext(config=cfg, platform_ops=MagicMock())
    res = reg.dispatch(Intent("open_path", {"name": "загрузки"}), ctx)
    ctx.platform_ops.open_path.assert_called_once_with("~/Downloads")
    assert res.success


def test_open_path_empty_fails():
    reg = Registry()
    files.register(reg)
    ctx = ExecutorContext(config=AppConfig(), platform_ops=MagicMock())
    res = reg.dispatch(Intent("open_path", {"name": ""}), ctx)
    assert res.success is False
