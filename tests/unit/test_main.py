from unittest.mock import MagicMock
from voice_assistant.main import Pipeline
from voice_assistant.config import AppConfig
from voice_assistant.core.types import (
    AudioSegment, Transcript, Intent, ExecutionResult,
)
import numpy as np


def test_pipeline_processes_one_segment_end_to_end():
    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой telegram", "ru", 0.9, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "telegram"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult.ok(
        message="ok", tts_response="Открыл")
    feedback = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    seg = AudioSegment(np.zeros(8000, dtype=np.int16), 16000)
    pipe.process_segment(seg)

    asr.transcribe.assert_called_once()
    nlu.route.assert_called_once()
    registry.dispatch.assert_called_once()
    feedback.emit.assert_called_once()


def test_low_confidence_transcript_skips_dispatch():
    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("...", "ru", 0.1, 200)
    nlu = MagicMock()
    registry = MagicMock()
    feedback = MagicMock()
    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    pipe.process_segment(AudioSegment(np.zeros(3200, dtype=np.int16), 16000))
    registry.dispatch.assert_not_called()
    feedback.emit.assert_called_once()


def test_whitespace_transcript_skips_dispatch():
    """Whitespace-only transcript hits the empty-text branch."""
    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("   ", "ru", 0.95, 100)
    nlu = MagicMock()
    registry = MagicMock()
    feedback = MagicMock()
    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    pipe.process_segment(AudioSegment(np.zeros(1600, dtype=np.int16), 16000))
    registry.dispatch.assert_not_called()
    feedback.emit.assert_called_once()
    assert feedback.emit.call_args.kwargs.get("success") is False


def test_unknown_intent_skips_dispatch():
    """Unknown intent from NLU hits the unknown-intent branch."""
    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("бла бла", "ru", 0.9, 300)
    nlu = MagicMock()
    nlu.route.return_value = Intent.unknown()
    registry = MagicMock()
    feedback = MagicMock()
    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    pipe.process_segment(AudioSegment(np.zeros(4800, dtype=np.int16), 16000))
    registry.dispatch.assert_not_called()
    feedback.emit.assert_called_once()
    assert feedback.emit.call_args.kwargs.get("success") is False


def test_failed_dispatch_propagates_success_false():
    """ExecutionResult with success=False forwards to feedback.emit(..., success=False)."""
    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой telegram", "ru", 0.9, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "telegram"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult.fail("boom")
    feedback = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    registry.dispatch.assert_called_once()
    feedback.emit.assert_called_once()
    assert feedback.emit.call_args.kwargs.get("success") is False
