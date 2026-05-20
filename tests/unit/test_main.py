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


def test_build_uses_composite_when_tts_enabled(tmp_path, monkeypatch):
    """When cfg.tts.enabled, _build must wire a CompositeFeedback that
    contains both CLIFeedback and PiperFeedback. When disabled, just CLI."""
    from voice_assistant.feedback.composite import CompositeFeedback
    from voice_assistant.feedback.cli import CLIFeedback
    from voice_assistant.feedback.piper import PiperFeedback

    # Skip heavy parts of _build (ASR model load, etc.) by mocking
    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine",
                        MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VoiceModelStore", MagicMock())

    # Minimal commands.yaml and default.yaml
    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n', encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        f"tts:\n  enabled: true\n  voice: ru_RU-irina-medium\n"
        f"  voices_dir: {tmp_path / 'voices'}\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))

    assert isinstance(feedback, CompositeFeedback)
    types = [type(s).__name__ for s in feedback._sinks]
    assert "CLIFeedback" in types
    assert "PiperFeedback" in types


def test_build_falls_back_to_cli_when_voices_dir_unwritable(tmp_path, monkeypatch):
    """If VoiceModelStore construction fails (e.g. unwritable dir), _build
    must drop Piper and return CLIFeedback alone."""
    from voice_assistant.feedback.cli import CLIFeedback

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())

    # VoiceModelStore.__init__ raises PermissionError
    bad_store = MagicMock(side_effect=PermissionError("read-only fs"))
    monkeypatch.setattr("voice_assistant.main.VoiceModelStore", bad_store)

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n', encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        f"tts:\n  enabled: true\n  voice: ru_RU-irina-medium\n"
        f"  voices_dir: {tmp_path / 'voices'}\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))
    assert isinstance(feedback, CLIFeedback)


def test_ptt_state_change_held_calls_feedback_cancel(monkeypatch, tmp_path):
    """Pressing PTT must call feedback.cancel() so any in-flight TTS aborts."""
    from voice_assistant.main import _build

    captured_callback = {}

    def _capture_ptt(key, cb):
        captured_callback["cb"] = cb
        return MagicMock()

    monkeypatch.setattr("voice_assistant.main.PushToTalk", _capture_ptt)
    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n', encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n", encoding="utf-8")

    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))

    # Swap in a spyable feedback so we can detect cancel()
    feedback.cancel = MagicMock()
    pipe.feedback = feedback  # not strictly needed for this test

    # Force on_state_change to be the captured callback bound to the closure
    on_state_change = captured_callback["cb"]
    on_state_change(True)
    feedback.cancel.assert_called_once()


def test_build_wraps_nlu_in_llm_fallback_when_enabled(tmp_path, monkeypatch):
    """When cfg.llm.enabled, _build wraps RulesRouter in LLMFallbackRouter."""
    from voice_assistant.nlu.llm_fallback import LLMFallbackRouter
    from voice_assistant.nlu.rules import RulesRouter

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    # Mock OllamaClient so we don't try to connect to a real server
    monkeypatch.setattr("voice_assistant.main.OllamaClient", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: true\n  model: qwen2.5:3b-instruct\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))
    assert isinstance(pipe.nlu, LLMFallbackRouter)
    # And the primary inside is still RulesRouter
    assert isinstance(pipe.nlu._primary, RulesRouter)


def test_build_uses_plain_rules_router_when_llm_disabled(tmp_path, monkeypatch):
    """When cfg.llm.enabled is false, NLU is RulesRouter alone (no wrapping)."""
    from voice_assistant.nlu.rules import RulesRouter
    from voice_assistant.nlu.llm_fallback import LLMFallbackRouter

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))
    assert isinstance(pipe.nlu, RulesRouter)
    assert not isinstance(pipe.nlu, LLMFallbackRouter)


def test_build_wraps_in_composite_when_wake_enabled(tmp_path, monkeypatch):
    """When wake.enabled, _build wraps PushToTalk and WakeWordActivator in a
    CompositeActivator."""
    from voice_assistant.activation.composite import CompositeActivator
    from voice_assistant.activation.wake_word import WakeWordActivator

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    monkeypatch.setattr("voice_assistant.main.WakeModelStore", MagicMock())
    monkeypatch.setattr("voice_assistant.main.WakeWordActivator", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: true\n  model: hey_jarvis\n"
        f"  models_dir: {tmp_path / 'wake-models'}\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))
    assert isinstance(ptt, CompositeActivator)


def test_build_keeps_plain_ptt_when_wake_disabled(tmp_path, monkeypatch):
    from voice_assistant.activation.composite import CompositeActivator

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", lambda *a, **k: MagicMock(name="ptt"))
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))
    assert not isinstance(ptt, CompositeActivator)


def test_build_drops_wake_when_store_fails(tmp_path, monkeypatch):
    """If WakeModelStore raises, _build falls back to plain PushToTalk."""
    from voice_assistant.activation.composite import CompositeActivator

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", lambda *a, **k: MagicMock(name="ptt"))
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())

    bad_store = MagicMock(side_effect=RuntimeError("disk full"))
    monkeypatch.setattr("voice_assistant.main.WakeModelStore", bad_store)

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: true\n  model: hey_jarvis\n"
        f"  models_dir: {tmp_path / 'wake-models'}\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback = _build(str(tmp_path / "default.yaml"))
    # Wake construction failed → ptt is the plain PushToTalk, not a Composite
    assert not isinstance(ptt, CompositeActivator)


def test_request_shutdown_sets_event_and_puts_stop_and_cancels_feedback():
    import threading as _t
    from voice_assistant.main import _request_shutdown
    from voice_assistant.core.queues import STOP

    stop_evt = _t.Event()
    qs = MagicMock()
    qs.speech_q = MagicMock()
    feedback = MagicMock()

    _request_shutdown(stop_evt, qs, feedback)

    assert stop_evt.is_set()
    qs.speech_q.put_nowait.assert_called_once_with(STOP)
    feedback.cancel.assert_called_once()


def test_request_shutdown_swallows_queue_full():
    import queue as _q
    import threading as _t
    from voice_assistant.main import _request_shutdown

    stop_evt = _t.Event()
    qs = MagicMock()
    qs.speech_q = MagicMock()
    qs.speech_q.put_nowait.side_effect = _q.Full()
    feedback = MagicMock()

    # Must NOT raise even when queue is full
    _request_shutdown(stop_evt, qs, feedback)
    assert stop_evt.is_set()
    feedback.cancel.assert_called_once()


def test_request_shutdown_swallows_feedback_cancel_failure():
    import threading as _t
    from voice_assistant.main import _request_shutdown

    stop_evt = _t.Event()
    qs = MagicMock()
    qs.speech_q = MagicMock()
    feedback = MagicMock()
    feedback.cancel.side_effect = RuntimeError("boom")

    # Must NOT propagate the exception
    _request_shutdown(stop_evt, qs, feedback)
    assert stop_evt.is_set()
