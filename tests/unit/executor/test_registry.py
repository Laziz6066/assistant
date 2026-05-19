import pytest
from voice_assistant.executor.registry import register_intent, Registry
from voice_assistant.core.types import Intent, ExecutionResult


def test_register_and_dispatch():
    reg = Registry()

    @register_intent("ping", registry=reg)
    def _ping(slots, ctx):
        return ExecutionResult.ok("pong")

    res = reg.dispatch(Intent(name="ping", slots={}), ctx=None)
    assert res.success and res.message == "pong"


def test_unknown_intent_returns_fail():
    reg = Registry()
    res = reg.dispatch(Intent.unknown(), ctx=None)
    assert res.success is False


def test_handler_exception_is_contained():
    reg = Registry()

    @register_intent("boom", registry=reg)
    def _boom(slots, ctx):
        raise RuntimeError("kaboom")

    res = reg.dispatch(Intent(name="boom", slots={}), ctx=None)
    assert res.success is False
    assert "kaboom" in res.message
