from __future__ import annotations
import math
import numpy as np
from loguru import logger
from voice_assistant.asr.base import ASREngine
from voice_assistant.core.types import AudioSegment, Transcript


def _resolve_device(device: str) -> tuple[str, str]:
    if device == "auto":
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda", "int8_float16"
        except Exception:
            pass
        return "cpu", "int8"
    if device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning("CUDA requested but unavailable, falling back to CPU")
                return "cpu", "int8"
        except Exception:
            return "cpu", "int8"
    return device, ""


class FasterWhisperEngine(ASREngine):
    def __init__(self, model: str, device: str, compute_type: str,
                 language: str, model_obj=None):
        self.language = language
        if model_obj is not None:
            self._model = model_obj
        else:
            from faster_whisper import WhisperModel
            dev, fallback_ct = _resolve_device(device)
            ct = fallback_ct or compute_type
            logger.info(f"Loading whisper {model} on {dev} ({ct})")
            self._model = WhisperModel(model, device=dev, compute_type=ct)

    def transcribe(self, segment: AudioSegment) -> Transcript:
        audio = segment.samples.astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(
            audio, language=self.language, beam_size=5)
        seg_list = list(segments)
        text = " ".join(s.text.strip() for s in seg_list).strip()
        if seg_list:
            avg_lp = sum(s.avg_logprob for s in seg_list) / len(seg_list)
            confidence = max(0.0, min(1.0, math.exp(avg_lp)))
        else:
            confidence = 0.0
        return Transcript(
            text=text,
            language=getattr(info, "language", self.language),
            confidence=confidence,
            duration_ms=segment.duration_ms,
        )
