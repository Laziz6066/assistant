from unittest.mock import MagicMock

from voice_assistant.executor.plugins.dictation import (
    _start_dictation, _stop_dictation, register,
)
from voice_assistant.executor.registry import Registry
from voice_assistant.dictation.mode_store import ModeStore


def test_start_dictation_handler_toggles_mode_store():
    ctx = MagicMock()
    store = ModeStore()
    ctx.mode_store = store
    result = _start_dictation({}, ctx)
    assert store.is_dictation() is True
    assert result.success is True
    assert "иктовк" in result.tts_response.lower() or "иктуй" in result.tts_response.lower()


def test_stop_dictation_handler_toggles_mode_store():
    ctx = MagicMock()
    store = ModeStore()
    store.start_dictation()  # pre-condition
    ctx.mode_store = store
    result = _stop_dictation({}, ctx)
    assert store.is_command() is True
    assert result.success is True


def test_start_dictation_with_none_mode_store_returns_fail():
    """When dictation feature is disabled, mode_store is None."""
    ctx = MagicMock()
    ctx.mode_store = None
    result = _start_dictation({}, ctx)
    assert result.success is False
    assert "выключен" in result.message.lower() or "выключен" in result.tts_response.lower()


def test_stop_dictation_with_none_mode_store_is_ok():
    """stop_dictation gracefully no-ops when feature is disabled — user
    already wasn't in dictation, so 'Готово' is the right response."""
    ctx = MagicMock()
    ctx.mode_store = None
    result = _stop_dictation({}, ctx)
    assert result.success is True


def test_register_adds_both_intents():
    reg = Registry()
    register(reg)
    assert "start_dictation" in reg._handlers
    assert "stop_dictation" in reg._handlers
