import queue as _q
import threading
from unittest.mock import MagicMock
from voice_assistant.main import Pipeline, _worker
from voice_assistant.config import AppConfig
from voice_assistant.core.queues import STOP
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


def test_worker_survives_iteration_exception():
    """A VAD or ASR exception must NOT kill the worker; it should
    emit a failure message and continue to the next iteration."""
    vad = MagicMock()
    vad.segment.side_effect = RuntimeError("boom")
    feedback = MagicMock()
    pipe = MagicMock(spec=Pipeline)
    pipe.feedback = feedback

    qs = MagicMock()
    qs.speech_q = _q.Queue()
    qs.speech_q.put(b"raw-bytes")
    qs.speech_q.put(STOP)

    stop_evt = threading.Event()
    _worker(pipe, qs, vad, stop_evt)

    feedback.emit.assert_called_with("Ошибка обработки", success=False)
    # process_segment must not be called when vad.segment raised
    pipe.process_segment.assert_not_called()


def test_worker_survives_pipeline_exception():
    """An exception from pipe.process_segment must also be caught."""
    from voice_assistant.core.types import AudioSegment as _Seg
    vad = MagicMock()
    vad.segment.return_value = _Seg(np.zeros(1600, dtype=np.int16), 16000)
    feedback = MagicMock()
    pipe = MagicMock(spec=Pipeline)
    pipe.feedback = feedback
    pipe.process_segment.side_effect = RuntimeError("asr blew up")

    qs = MagicMock()
    qs.speech_q = _q.Queue()
    qs.speech_q.put(b"raw-bytes")
    qs.speech_q.put(STOP)

    stop_evt = threading.Event()
    _worker(pipe, qs, vad, stop_evt)

    feedback.emit.assert_called_with("Ошибка обработки", success=False)


def test_transcript_text_not_logged_when_store_transcripts_false(monkeypatch):
    """With store_transcripts=False, the raw transcript text must not
    appear in any logger.info call from Pipeline.process_segment."""
    sentinel = "SECRETPHRASE12345"
    calls: list[str] = []
    monkeypatch.setattr("voice_assistant.main.logger.info",
                        lambda msg: calls.append(msg))

    cfg = AppConfig()  # store_transcripts defaults to False
    assert cfg.store_transcripts is False
    asr = MagicMock()
    asr.transcribe.return_value = Transcript(sentinel, "ru", 0.9, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "x"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult.ok(
        message="ok", tts_response="done")
    feedback = MagicMock()
    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    assert calls, "expected at least one logger.info call"
    assert not any(sentinel in c for c in calls), (
        f"transcript sentinel leaked into logs: {calls}"
    )


def test_transcript_text_logged_when_store_transcripts_true(monkeypatch):
    """With store_transcripts=True, the transcript text IS logged."""
    sentinel = "LOUDPHRASE67890"
    calls: list[str] = []
    monkeypatch.setattr("voice_assistant.main.logger.info",
                        lambda msg: calls.append(msg))

    cfg = AppConfig(store_transcripts=True)
    asr = MagicMock()
    asr.transcribe.return_value = Transcript(sentinel, "ru", 0.9, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "x"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult.ok(
        message="ok", tts_response="done")
    feedback = MagicMock()
    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    assert any(sentinel in c for c in calls), (
        f"transcript should appear in logs when store_transcripts=True: {calls}"
    )


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
