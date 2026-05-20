from __future__ import annotations
import queue
import signal
import threading
from pathlib import Path
from loguru import logger

from voice_assistant.config import load_config, AppConfig
from voice_assistant.core.queues import PipelineQueues, STOP
from voice_assistant.core.types import AudioSegment
from voice_assistant.utils.logging import setup_logging
from voice_assistant.utils.platform import get_platform_ops
from voice_assistant.audio.capture import AudioCapture
from voice_assistant.audio.vad import VADSegmenter
from voice_assistant.activation.base import Activator
from voice_assistant.activation.composite import CompositeActivator
from voice_assistant.activation.hotkey import PushToTalk
from voice_assistant.activation.models_store import WakeModelStore
from voice_assistant.activation.wake_word import WakeWordActivator
from voice_assistant.asr.base import ASREngine
from voice_assistant.asr.faster_whisper_engine import FasterWhisperEngine
from voice_assistant.nlu.base import NLURouter
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.nlu.llm_fallback import LLMFallbackRouter
from voice_assistant.nlu.ollama_client import OllamaClient
from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.executor.registry import global_registry, Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.executor.plugins import register_all
from voice_assistant.feedback.base import FeedbackSink
from voice_assistant.feedback.cli import CLIFeedback
from voice_assistant.feedback.composite import CompositeFeedback
from voice_assistant.feedback.piper import PiperFeedback
from voice_assistant.feedback.voice_models import VoiceModelStore
from voice_assistant.ui.tray import SystemTray


class Pipeline:
    def __init__(self, config: AppConfig, asr: ASREngine, nlu: NLURouter,
                 registry: Registry, ctx: ExecutorContext,
                 feedback: FeedbackSink,
                 context_store: ContextStore | None = None):
        self.config = config
        self.asr = asr
        self.nlu = nlu
        self.registry = registry
        self.ctx = ctx
        self.feedback = feedback
        self.context_store = context_store

    def process_segment(self, segment: AudioSegment) -> None:
        transcript = self.asr.transcribe(segment)
        if self.config.store_transcripts:
            logger.info(f"ASR: '{transcript.text}' "
                        f"(conf={transcript.confidence:.2f})")
        else:
            logger.info(f"ASR conf={transcript.confidence:.2f} "
                        f"(transcript redacted)")
        if transcript.confidence < self.config.asr.min_confidence \
                or not transcript.text.strip():
            self.feedback.emit("Не понял, повтори", success=False)
            return
        intent = self.nlu.route(transcript)
        if intent.name == "unknown":
            self.feedback.emit("Не понял, повтори", success=False)
            return
        result = self.registry.dispatch(intent, self.ctx)
        logger.info(f"intent={intent.name} success={result.success}")
        if result.success and self.context_store is not None:
            self.context_store.add(intent)
        self.feedback.emit(result.tts_response, success=result.success)


def _build(config_path: str) -> tuple[Pipeline, PipelineQueues,
                                       AudioCapture, Activator, VADSegmenter,
                                       FeedbackSink, SystemTray | None]:
    cfg = load_config(config_path)
    setup_logging(level=cfg.log_level)
    register_all()
    ops = get_platform_ops()
    ctx = ExecutorContext(config=cfg, platform_ops=ops)
    asr = FasterWhisperEngine(
        model=cfg.asr.model, device=cfg.asr.device,
        compute_type=cfg.asr.compute_type, language=cfg.asr.language)
    nlu: NLURouter = RulesRouter(
        commands_path=str(Path(config_path).parent / "commands.yaml"),
        fuzzy_threshold=cfg.nlu.fuzzy_threshold)
    if cfg.llm.enabled:
        ollama_client = OllamaClient(
            host=cfg.llm.host, model=cfg.llm.model,
            timeout_s=cfg.llm.timeout_s,
            temperature=cfg.llm.temperature,
            min_confidence=cfg.llm.min_confidence)
        nlu = LLMFallbackRouter(
            primary=nlu, client=ollama_client,
            commands_path=Path(config_path).parent / "commands.yaml",
            app_aliases=cfg.app_aliases)
    if cfg.tts.enabled:
        try:
            store = VoiceModelStore(cfg.tts.voices_dir)
            piper = PiperFeedback(voice=cfg.tts.voice, store=store,
                                   length_scale=cfg.tts.length_scale)
            feedback: FeedbackSink = CompositeFeedback([CLIFeedback(), piper])
        except OSError as e:
            logger.error(f"TTS disabled — voices_dir unusable: {e}")
            feedback = CLIFeedback()
    else:
        feedback = CLIFeedback()
    pipe = Pipeline(cfg, asr, nlu, global_registry(), ctx, feedback)

    qs = PipelineQueues()
    capture = AudioCapture(cfg.audio.sample_rate, cfg.audio.ring_seconds,
                           cfg.audio.input_device)
    vad = VADSegmenter(cfg.audio.sample_rate, cfg.vad.threshold,
                       cfg.vad.min_speech_ms, cfg.vad.max_speech_ms)

    import threading as _threading
    state_lock = _threading.Lock()
    holders: set[str] = set()
    mark = 0

    def on_state_change(held: bool, source: str = "ptt") -> None:
        nonlocal mark
        with state_lock:
            if held:
                first = not holders
                holders.add(source)
                if first:
                    feedback.cancel()
                    mark = len(capture.ring.snapshot())
            else:
                holders.discard(source)
                if not holders:
                    raw = capture.ring.snapshot()[mark:]
                    qs.speech_q.put(raw)

    ptt: Activator = PushToTalk(cfg.hotkey.push_to_talk, on_state_change)
    activators: list[Activator] = [ptt]
    if cfg.wake.enabled:
        try:
            wake_store = WakeModelStore(cfg.wake.models_dir)
            wake = WakeWordActivator(
                model=cfg.wake.model, store=wake_store,
                capture=capture,
                threshold=cfg.wake.threshold,
                silence_ms=cfg.wake.silence_ms,
                max_speech_ms=cfg.wake.max_speech_ms,
                on_state_change=on_state_change,
                _sample_rate=cfg.audio.sample_rate,
            )
            activators.append(wake)
        except Exception as e:
            logger.error(f"wake disabled — setup failed: {e}")
    if len(activators) > 1:
        ptt = CompositeActivator(activators)

    tray: SystemTray | None = None
    if cfg.tray.enabled:
        try:
            tray = SystemTray(quit_callback=lambda: None, version="0.1.0")
        except Exception as e:
            logger.error(f"tray disabled — setup failed: {e}")
            tray = None

    return pipe, qs, capture, ptt, vad, feedback, tray


def _request_shutdown(stop_evt: threading.Event,
                       qs: PipelineQueues,
                       feedback: FeedbackSink) -> None:
    """Idempotent shutdown trigger used by SIGINT and the tray Quit menu.

    Sets the worker's stop event, puts the STOP sentinel onto the speech
    queue (swallowing queue.Full), and cancels any in-flight feedback.
    Safe to call multiple times.
    """
    logger.info("shutting down")
    stop_evt.set()
    try:
        qs.speech_q.put_nowait(STOP)
    except queue.Full:
        pass
    try:
        feedback.cancel()
    except Exception:
        logger.exception("feedback.cancel during shutdown failed")


def _worker(pipe: Pipeline, qs: PipelineQueues, vad: VADSegmenter,
            stop_evt: threading.Event) -> None:
    while not stop_evt.is_set():
        try:
            raw = qs.speech_q.get(timeout=0.5)
        except queue.Empty:
            continue
        if raw is STOP:
            break
        try:
            segment = vad.segment(raw)
            if segment is None:
                pipe.feedback.emit("Не расслышал", success=False)
                continue
            pipe.process_segment(segment)
        except Exception:
            logger.exception("worker iteration failed")
            pipe.feedback.emit("Ошибка обработки", success=False)


def main() -> int:
    config_path = "config/default.yaml"
    pipe, qs, capture, ptt, vad, feedback, tray = _build(config_path)
    stop_evt = threading.Event()
    try:
        capture.start()
    except Exception as e:
        logger.error(f"microphone unavailable: {e}")
        return 1
    feedback.start()

    def _shutdown(*_):
        _request_shutdown(stop_evt, qs, feedback)

    signal.signal(signal.SIGINT, _shutdown)
    if tray is not None:
        tray.set_quit_callback(lambda: _shutdown())
        try:
            tray.start()
        except Exception:
            logger.exception("tray.start failed")
            tray = None
    ptt.start()
    worker = threading.Thread(target=_worker, args=(pipe, qs, vad, stop_evt),
                              daemon=True)
    worker.start()
    logger.info("ready — hold push-to-talk key and speak")
    worker.join()
    if tray is not None:
        try:
            tray.stop()
        except Exception:
            logger.exception("tray.stop failed")
    feedback.stop()
    ptt.stop()
    capture.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
