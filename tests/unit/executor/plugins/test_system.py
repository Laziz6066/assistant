from unittest.mock import MagicMock
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import ExecutionResult, Intent
import voice_assistant.executor.plugins.system as sysmod
import time


def _ctx(ops=None):
    return ExecutorContext(config=AppConfig(), platform_ops=ops or MagicMock())


def test_volume_set_calls_platform():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    reg.dispatch(Intent("volume_set", {"level": 40}), _ctx(ops))
    ops.set_volume.assert_called_once_with(40)


def test_lock_calls_platform():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    res = reg.dispatch(Intent("lock_screen", {}), _ctx(ops))
    ops.lock_screen.assert_called_once()
    assert res.success


def test_shutdown_requires_confirmation_not_executed_immediately():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    res = reg.dispatch(Intent("shutdown", {}), _ctx(ops))
    ops.shutdown.assert_not_called()
    assert res.success is True
    assert "подтверд" in res.tts_response.lower()


def test_confirm_yes_executes_pending_shutdown():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    ctx = _ctx(ops)
    reg.dispatch(Intent("shutdown", {}), ctx)
    res = reg.dispatch(Intent("confirm_yes", {}), ctx)
    ops.shutdown.assert_called_once_with(reboot=False)
    assert res.success


def test_confirm_yes_with_no_pending_action_is_noop():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    res = reg.dispatch(Intent("confirm_yes", {}), _ctx(ops))
    ops.shutdown.assert_not_called()
    assert res.success
    assert "нечего" in res.tts_response.lower()


def test_confirm_yes_expires_after_timeout(monkeypatch):
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    ctx = _ctx(ops)

    # Arm shutdown
    reg.dispatch(Intent("shutdown", {}), ctx)

    # Advance monotonic clock past the confirm window
    real_monotonic = time.monotonic
    start = real_monotonic()
    monkeypatch.setattr(
        sysmod.time, "monotonic",
        lambda: start + sysmod.CONFIRM_TIMEOUT_S + 1.0)

    res = reg.dispatch(Intent("confirm_yes", {}), ctx)
    ops.shutdown.assert_not_called()
    assert res.success
    assert "вышло" in res.tts_response.lower() or "отмена" in res.tts_response.lower()
