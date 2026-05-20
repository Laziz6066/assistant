from unittest.mock import MagicMock
import pytest
from voice_assistant.feedback.composite import CompositeFeedback
from voice_assistant.feedback.base import FeedbackSink


class _StubSink(FeedbackSink):
    def __init__(self):
        self.emits = []
        self.cancels = 0
        self.starts = 0
        self.stops = 0

    def emit(self, message, success=True):
        self.emits.append((message, success))

    def cancel(self):
        self.cancels += 1

    def start(self):
        self.starts += 1

    def stop(self):
        self.stops += 1


def test_emit_fans_out_in_order():
    a, b = _StubSink(), _StubSink()
    comp = CompositeFeedback([a, b])
    comp.emit("hello", success=True)
    assert a.emits == [("hello", True)]
    assert b.emits == [("hello", True)]


def test_emit_continues_when_one_sink_raises():
    bad = MagicMock(spec=FeedbackSink)
    bad.emit.side_effect = RuntimeError("boom")
    good = _StubSink()
    comp = CompositeFeedback([bad, good])
    comp.emit("hello", success=False)
    # Good sink must still have been called despite bad sink raising
    assert good.emits == [("hello", False)]


def test_cancel_fans_out():
    a, b = _StubSink(), _StubSink()
    comp = CompositeFeedback([a, b])
    comp.cancel()
    assert a.cancels == 1 and b.cancels == 1


def test_start_and_stop_fan_out():
    a, b = _StubSink(), _StubSink()
    comp = CompositeFeedback([a, b])
    comp.start()
    comp.stop()
    assert a.starts == 1 and b.starts == 1
    assert a.stops == 1 and b.stops == 1


def test_lifecycle_continues_when_one_sink_raises():
    bad = MagicMock(spec=FeedbackSink)
    bad.start.side_effect = RuntimeError("can't start")
    bad.stop.side_effect = RuntimeError("can't stop")
    bad.cancel.side_effect = RuntimeError("can't cancel")
    good = _StubSink()
    comp = CompositeFeedback([bad, good])
    comp.start(); comp.cancel(); comp.stop()
    assert good.starts == 1 and good.cancels == 1 and good.stops == 1
