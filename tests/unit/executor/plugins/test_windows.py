from unittest.mock import MagicMock, patch
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.windows as win


def _ctx():
    return ExecutorContext(config=AppConfig(), platform_ops=MagicMock())


def test_minimize_all_sends_win_d():
    reg = Registry()
    win.register(reg)
    with patch.object(win, "_press") as press:
        res = reg.dispatch(Intent("minimize_all", {}), _ctx())
    press.assert_called_once_with("win", "d")
    assert res.success


def test_close_window_sends_alt_f4():
    reg = Registry()
    win.register(reg)
    with patch.object(win, "_press") as press:
        res = reg.dispatch(Intent("close_window", {}), _ctx())
    press.assert_called_once_with("alt", "f4")
    assert res.success


def test_switch_window_sends_alt_tab():
    reg = Registry()
    win.register(reg)
    with patch.object(win, "_press") as press:
        res = reg.dispatch(Intent("switch_window", {}), _ctx())
    press.assert_called_once_with("alt", "tab")
    assert res.success
