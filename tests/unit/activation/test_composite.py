from unittest.mock import MagicMock
from voice_assistant.activation.composite import CompositeActivator
from voice_assistant.activation.base import Activator


class _Stub(Activator):
    def __init__(self):
        self.started = 0
        self.stopped = 0
    def start(self) -> None:
        self.started += 1
    def stop(self) -> None:
        self.stopped += 1


def test_start_fans_out_to_all():
    a, b = _Stub(), _Stub()
    comp = CompositeActivator([a, b])
    comp.start()
    assert a.started == 1 and b.started == 1


def test_stop_fans_out_to_all():
    a, b = _Stub(), _Stub()
    comp = CompositeActivator([a, b])
    comp.stop()
    assert a.stopped == 1 and b.stopped == 1


def test_start_continues_when_one_child_raises():
    bad = MagicMock(spec=Activator)
    bad.start.side_effect = RuntimeError("boom")
    good = _Stub()
    comp = CompositeActivator([bad, good])
    comp.start()
    assert good.started == 1


def test_stop_continues_when_one_child_raises():
    bad = MagicMock(spec=Activator)
    bad.stop.side_effect = RuntimeError("boom")
    good = _Stub()
    comp = CompositeActivator([bad, good])
    comp.stop()
    assert good.stopped == 1
