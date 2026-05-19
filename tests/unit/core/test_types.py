import dataclasses
import numpy as np
import pytest
from voice_assistant.core.types import AudioSegment, Transcript, Intent, ExecutionResult


def test_dtos_are_frozen():
    t = Transcript(text="hi", language="ru", confidence=0.9, duration_ms=120)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.text = "bye"


def test_intent_unknown_helper():
    i = Intent.unknown()
    assert i.name == "unknown"
    assert i.slots == {}
    assert i.confidence == 0.0


def test_audio_segment_holds_samples():
    samples = np.zeros(1600, dtype=np.int16)
    seg = AudioSegment(samples=samples, sample_rate=16000)
    assert seg.duration_ms == 100


def test_execution_result_ok_and_fail():
    ok = ExecutionResult.ok("done", tts_response="готово")
    assert ok.success is True and ok.tts_response == "готово"
    fail = ExecutionResult.fail("boom")
    assert fail.success is False and fail.message == "boom"
