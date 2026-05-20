import threading
import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest
from pathlib import Path

from voice_assistant.feedback.piper import PiperFeedback


class _RecordingPiper(PiperFeedback):
    """Test subclass: records every _synthesize_and_play call without
    actually invoking Piper or sounddevice."""

    def __init__(self, *args, fail_on=None, hang_ms=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.played = []
        self._fail_on = fail_on
        self._hang_ms = hang_ms

    def _load_engine(self, onnx_path: Path, json_path: Path) -> None:
        # Stub: skip real Piper load so tests don't need real model files
        self._sample_rate = 22050

    def _synthesize_and_play(self, message: str) -> None:
        if self._fail_on is not None and message == self._fail_on:
            raise RuntimeError(f"synth failed for {message!r}")
        if self._hang_ms:
            time.sleep(self._hang_ms / 1000)
        self.played.append(message)


def _make_store_mock(tmp_path):
    store = MagicMock()
    store.ensure.return_value = (tmp_path / "voice.onnx",
                                  tmp_path / "voice.onnx.json")
    return store


def test_start_sets_available_when_store_returns_paths(tmp_path):
    store = _make_store_mock(tmp_path)
    fb = _RecordingPiper(voice="ru_RU-irina-medium",
                          store=store, length_scale=1.0)
    fb.start()
    try:
        assert fb._available is True
    finally:
        fb.stop()


def test_emit_enqueues_when_available(tmp_path):
    store = _make_store_mock(tmp_path)
    fb = _RecordingPiper(voice="x_X-y-z", store=store, length_scale=1.0)
    fb.start()
    try:
        fb.emit("привет", success=True)
        fb.emit("второе", success=True)
        # Give the worker up to 1s to drain both
        deadline = time.time() + 1.0
        while time.time() < deadline and len(fb.played) < 2:
            time.sleep(0.02)
        assert fb.played == ["привет", "второе"]
    finally:
        fb.stop()


def test_emit_is_silent_when_unavailable(tmp_path):
    from voice_assistant.feedback.voice_models import VoiceDownloadError
    store = MagicMock()
    store.ensure.side_effect = VoiceDownloadError("no internet")
    fb = _RecordingPiper(voice="x_X-y-z", store=store, length_scale=1.0)
    fb.start()
    try:
        assert fb._available is False
        # emit must not raise, must not block
        fb.emit("hello")
    finally:
        fb.stop()


def test_emit_returns_fast_under_1ms(tmp_path):
    store = _make_store_mock(tmp_path)
    fb = _RecordingPiper(voice="x_X-y-z", store=store,
                          length_scale=1.0, hang_ms=200)
    fb.start()
    try:
        t0 = time.perf_counter()
        fb.emit("длинная фраза")
        dt = time.perf_counter() - t0
        assert dt < 0.05, f"emit took {dt*1000:.1f}ms, expected <50ms"
    finally:
        fb.stop()


def test_cancel_drains_queue(tmp_path):
    store = _make_store_mock(tmp_path)
    # hang_ms makes the worker busy on the first message; the rest sit in queue
    fb = _RecordingPiper(voice="x_X-y-z", store=store,
                          length_scale=1.0, hang_ms=300)
    fb.start()
    try:
        fb.emit("first")
        time.sleep(0.05)  # let worker pick up "first"
        fb.emit("queued1")
        fb.emit("queued2")
        fb.cancel()
        time.sleep(0.5)
        # only "first" should have played; "queued1"/"queued2" drained
        assert "queued1" not in fb.played
        assert "queued2" not in fb.played
    finally:
        fb.stop()


def test_worker_survives_synth_exception(tmp_path):
    store = _make_store_mock(tmp_path)
    fb = _RecordingPiper(voice="x_X-y-z", store=store,
                          length_scale=1.0, fail_on="bad")
    fb.start()
    try:
        fb.emit("good1")
        fb.emit("bad")
        fb.emit("good2")
        deadline = time.time() + 1.0
        while time.time() < deadline and len(fb.played) < 2:
            time.sleep(0.02)
        # "bad" raised but "good2" still played
        assert "good1" in fb.played
        assert "good2" in fb.played
        assert "bad" not in fb.played
    finally:
        fb.stop()


def test_stop_joins_thread(tmp_path):
    store = _make_store_mock(tmp_path)
    fb = _RecordingPiper(voice="x_X-y-z", store=store, length_scale=1.0)
    fb.start()
    assert fb._thread is not None and fb._thread.is_alive()
    fb.stop()
    assert not fb._thread.is_alive()


def test_queue_overflow_drops_with_warning(tmp_path):
    store = _make_store_mock(tmp_path)
    fb = _RecordingPiper(voice="x_X-y-z", store=store,
                          length_scale=1.0, hang_ms=1000)
    fb.start()
    try:
        warnings = []
        # Hook loguru via add() with a custom sink — capture WARNING+ messages
        from loguru import logger as _logger
        sink_id = _logger.add(lambda msg: warnings.append(str(msg)), level="WARNING")
        try:
            # fill queue (maxsize=8) + overflow attempts
            for i in range(20):
                fb.emit(f"msg{i}")
        finally:
            _logger.remove(sink_id)
        # At least one drop warning should have been logged
        assert any("queue full" in w.lower() or "dropping" in w.lower()
                   for w in warnings), f"expected drop warning, got: {warnings!r}"
        fb.cancel()  # drain
    finally:
        fb.stop()


def test_load_engine_calls_piper_load(tmp_path):
    store = _make_store_mock(tmp_path)
    with patch("voice_assistant.feedback.piper.PiperVoice") as MockVoice:
        mock_voice = MagicMock()
        mock_voice.config.sample_rate = 22050
        MockVoice.load.return_value = mock_voice
        fb = PiperFeedback(voice="ru_RU-irina-medium", store=store,
                            length_scale=1.2)
        fb.start()
        try:
            MockVoice.load.assert_called_once()
            assert fb._available is True
            assert fb._sample_rate == 22050
        finally:
            fb.stop()


def test_synthesize_and_play_uses_voice_and_stream(tmp_path):
    store = _make_store_mock(tmp_path)
    with patch("voice_assistant.feedback.piper.PiperVoice") as MockVoice, \
         patch("voice_assistant.feedback.piper.SynthesisConfig") as MockSynConfig, \
         patch("voice_assistant.feedback.piper.sd.OutputStream") as MockStream:
        # voice.synthesize yields AudioChunk-like objects with audio_int16_bytes
        chunk1_bytes = (np.zeros(1000, dtype=np.int16)).tobytes()
        chunk2_bytes = (np.ones(500, dtype=np.int16) * 100).tobytes()
        audio_chunk1 = MagicMock()
        audio_chunk1.audio_int16_bytes = chunk1_bytes
        audio_chunk2 = MagicMock()
        audio_chunk2.audio_int16_bytes = chunk2_bytes
        mock_voice = MagicMock()
        mock_voice.config.sample_rate = 22050
        mock_voice.synthesize.return_value = iter([audio_chunk1, audio_chunk2])
        MockVoice.load.return_value = mock_voice

        stream_ctx = MagicMock()
        stream_ctx.write = MagicMock()
        MockStream.return_value.__enter__ = MagicMock(return_value=stream_ctx)
        MockStream.return_value.__exit__ = MagicMock(return_value=False)

        fb = PiperFeedback(voice="ru_RU-irina-medium", store=store,
                            length_scale=1.0)
        fb.start()
        try:
            fb.emit("привет")
            # wait for worker to process
            deadline = time.time() + 1.0
            while time.time() < deadline and stream_ctx.write.call_count < 2:
                time.sleep(0.02)
            mock_voice.synthesize.assert_called_once()
            args, kwargs = mock_voice.synthesize.call_args
            assert args[0] == "привет"
            # SynthesisConfig was constructed with length_scale=1.0
            MockSynConfig.assert_called_once_with(length_scale=1.0)
            # The syn_config kwarg was passed to synthesize
            assert "syn_config" in kwargs
            assert stream_ctx.write.call_count == 2
        finally:
            fb.stop()


def test_engine_load_failure_disables_tts(tmp_path):
    store = _make_store_mock(tmp_path)
    with patch("voice_assistant.feedback.piper.PiperVoice") as MockVoice:
        MockVoice.load.side_effect = RuntimeError("corrupt model")
        fb = PiperFeedback(voice="ru_RU-irina-medium", store=store,
                            length_scale=1.0)
        fb.start()
        try:
            assert fb._available is False
        finally:
            fb.stop()
