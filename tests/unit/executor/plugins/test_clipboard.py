from unittest.mock import MagicMock, patch
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.clipboard as cb


def _ctx():
    return ExecutorContext(config=AppConfig(), platform_ops=MagicMock())


def test_copy_sends_ctrl_c():
    reg = Registry()
    cb.register(reg)
    with patch.object(cb, "_press") as press:
        res = reg.dispatch(Intent("clipboard_copy", {}), _ctx())
    press.assert_called_once_with("ctrl", "c")
    assert res.success


def test_paste_sends_ctrl_v():
    reg = Registry()
    cb.register(reg)
    with patch.object(cb, "_press") as press:
        res = reg.dispatch(Intent("clipboard_paste", {}), _ctx())
    press.assert_called_once_with("ctrl", "v")
    assert res.success


def test_read_returns_clipboard_text():
    reg = Registry()
    cb.register(reg)
    with patch.object(cb, "_read_clipboard", return_value="привет"):
        res = reg.dispatch(Intent("clipboard_read", {}), _ctx())
    assert "привет" in res.tts_response
    assert res.success
