from voice_assistant.feedback.base import FeedbackSink


class _StubSink(FeedbackSink):
    def emit(self, message: str, success: bool = True) -> None:
        pass


def test_default_lifecycle_methods_are_no_ops():
    """start/stop/cancel must have no-op defaults so simple sinks (like CLI)
    don't need to override them."""
    sink = _StubSink()
    sink.start()
    sink.cancel()
    sink.stop()
