"""Measure ASR latency and rough WER across models.

Usage: python scripts/benchmark_asr.py path/to/audio.wav "reference text"
"""
from __future__ import annotations
import sys
import time
import wave
import numpy as np
from voice_assistant.asr.faster_whisper_engine import FasterWhisperEngine
from voice_assistant.core.types import AudioSegment


def _load_wav(path: str) -> AudioSegment:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        frames = w.readframes(w.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16)
    return AudioSegment(samples=samples, sample_rate=sr)


def _wer(ref: str, hyp: str) -> float:
    r, h = ref.split(), hyp.split()
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + cost)
    return d[len(r)][len(h)] / max(1, len(r))


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    wav, ref = sys.argv[1], sys.argv[2]
    seg = _load_wav(wav)
    for model in ("small", "medium"):
        eng = FasterWhisperEngine(model=model, device="cuda",
                                  compute_type="int8_float16", language="ru")
        t0 = time.perf_counter()
        tr = eng.transcribe(seg)
        dt = time.perf_counter() - t0
        print(f"{model}: latency={dt:.2f}s wer={_wer(ref, tr.text):.2%} "
              f"text='{tr.text}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
