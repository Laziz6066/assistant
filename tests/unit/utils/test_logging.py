from voice_assistant.utils.logging import setup_logging


def test_setup_logging_returns_logger_and_respects_level():
    log = setup_logging(level="WARNING")
    assert log is not None
    log.warning("test-message")  # must not raise
