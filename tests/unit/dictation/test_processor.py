from unittest.mock import MagicMock

from voice_assistant.dictation.processor import DictationProcessor


def test_type_transcript_normalizes_then_types():
    ops = MagicMock()
    proc = DictationProcessor(platform_ops=ops)
    proc.type_transcript("привет мама точка")
    ops.type_text.assert_called_once_with("привет мама.")


def test_type_transcript_empty_string_no_platform_call():
    ops = MagicMock()
    proc = DictationProcessor(platform_ops=ops)
    proc.type_transcript("")
    ops.type_text.assert_not_called()


def test_type_transcript_whitespace_only_no_platform_call():
    ops = MagicMock()
    proc = DictationProcessor(platform_ops=ops)
    proc.type_transcript("    ")
    ops.type_text.assert_not_called()


def test_type_transcript_swallows_platform_exception():
    """If type_text raises, DictationProcessor does NOT propagate."""
    ops = MagicMock()
    ops.type_text.side_effect = RuntimeError("no keyboard")
    proc = DictationProcessor(platform_ops=ops)
    # Must not raise
    proc.type_transcript("привет")
