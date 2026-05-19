import numpy as np
from voice_assistant.audio.vad import VADSegmenter


class FakeVADModel:
    """Returns speech prob 0.9 for non-zero frames, 0.0 for silence."""
    def __call__(self, tensor, sr):
        import numpy as np
        arr = tensor.numpy() if hasattr(tensor, "numpy") else np.asarray(tensor)
        return type("T", (), {"item": lambda s: 0.9 if np.any(arr != 0) else 0.0})()


def test_rejects_too_short(monkeypatch):
    seg = VADSegmenter(sample_rate=16000, threshold=0.5,
                        min_speech_ms=300, max_speech_ms=15000,
                        model=FakeVADModel())
    samples = np.ones(1600, dtype=np.int16)  # 100ms < 300ms
    assert seg.segment(samples) is None


def test_accepts_valid_segment(monkeypatch):
    seg = VADSegmenter(sample_rate=16000, threshold=0.5,
                        min_speech_ms=300, max_speech_ms=15000,
                        model=FakeVADModel())
    samples = np.ones(16000, dtype=np.int16)  # 1000ms
    out = seg.segment(samples)
    assert out is not None
    assert out.sample_rate == 16000


def test_trims_too_long(monkeypatch):
    seg = VADSegmenter(sample_rate=16000, threshold=0.5,
                        min_speech_ms=300, max_speech_ms=15000,
                        model=FakeVADModel())
    samples = np.ones(16000 * 20, dtype=np.int16)  # 20s
    out = seg.segment(samples)
    assert out is not None
    assert out.duration_ms <= 15000
