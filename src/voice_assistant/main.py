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
from voice_assistant.activation.hotkey import PushToTalk
from voice_assistant.asr.base import ASREngine
from voice_assistant.asr.faster_whisper_engine import FasterWhisperEngine
from voice_assistant.nlu.base import NLURouter
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.executor.registry import global_registry, Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.executor.plugins import register_all
from voice_assistant.feedback.base import FeedbackSink
from voice_assistant.feedback.cli import CLIFeedback
from voice_assistant.feedback.composite import CompositeFeedback
from voice_assistant.feedback.piper import PiperFeedback
from voice_assistant.feedback.voice_models import VoiceModelStore


class Pipeline:
    def __init__(self, config: AppConfig, asr: ASREngine, nlu: NLURouter,
                 registry: Registry, ctx: ExecutorContext,
                 feedback: FeedbackSink):
        self.config = config
        self.asr = asr
        self.nlu = nlu
        self.registry = registry
        self.ctx = ctx
        self.feedback = feedback

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
        self.feedback.emit(result.tts_response, success=result.success)


def _build(config_path: str) -> tuple[Pipeline, PipelineQueues,
                                       AudioCapture, PushToTalk, VADSegmenter,
                                       FeedbackSink]:
    cfg = load_config(config_path)
    setup_logging(level=cfg.log_level)
    register_all()
    ops = get_platform_ops()
    ctx = ExecutorContext(config=cfg, platform_ops=ops)
    asr = FasterWhisperEngine(
        model=cfg.asr.model, device=cfg.asr.device,
        compute_type=cfg.asr.compute_type, language=cfg.asr.language)
    nlu = RulesRouter(
        commands_path=str(Path(config_path).parent / "commands.yaml"),
        fuzzy_threshold=cfg.nlu.fuzzy_threshold)
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

    mark = 0

    def on_state_change(held: bool) -> None:
        nonlocal mark
        if held:
            feedback.cancel()
            mark = len(capture.ring.snapshot())
        else:
            raw = capture.ring.snapshot()[mark:]
            qs.speech_q.put(raw)

    ptt = PushToTalk(cfg.hotkey.push_to_talk, on_state_change)
    return pipe, qs, capture, ptt, vad, feedback


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
    pipe, qs, capture, ptt, vad, feedback = _build(config_path)
    stop_evt = threading.Event()
    try:
        capture.start()
    except Exception as e:
        logger.error(f"microphone unavailable: {e}")
        return 1
    feedback.start()

    def _shutdown(*_):
        logger.info("shutting down")
        stop_evt.set()
        qs.speech_q.put(STOP)
        try:
            feedback.cancel()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _shutdown)
    ptt.start()
    worker = threading.Thread(target=_worker, args=(pipe, qs, vad, stop_evt),
                              daemon=True)
    worker.start()
    logger.info("ready — hold push-to-talk key and speak")
    worker.join()
    feedback.stop()
    ptt.stop()
    capture.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
