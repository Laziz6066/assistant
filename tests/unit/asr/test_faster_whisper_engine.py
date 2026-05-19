import numpy as np
from voice_assistant.asr.faster_whisper_engine import FasterWhisperEngine
from voice_assistant.core.types import AudioSegment


class FakeSeg:
    def __init__(self, text, logprob):
        self.text = text
        self.avg_logprob = logprob


class FakeModel:
    def transcribe(self, audio, language, beam_size):
        info = type("I", (), {"language": "ru", "language_probability": 0.95})()
        return [FakeSeg(" привет", -0.2), FakeSeg(" мир", -0.3)], info


def test_transcribe_joins_segments_and_maps_confidence():
    eng = FasterWhisperEngine(model="medium", device="cpu",
                              compute_type="int8", language="ru",
                              model_obj=FakeModel())
    seg = AudioSegment(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
    t = eng.transcribe(seg)
    assert t.text == "привет мир"
    assert t.language == "ru"
    assert 0.0 <= t.confidence <= 1.0
    assert t.duration_ms == 1000
