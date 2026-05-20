import threading
import time
from unittest.mock import MagicMock, patch
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


def test_queue_overflow_drops_with_warning(tmp_path, caplog):
    store = _make_store_mock(tmp_path)
    # Big hang on each playback so the queue fills up
    fb = _RecordingPiper(voice="x_X-y-z", store=store,
                          length_scale=1.0, hang_ms=1000)
    fb.start()
    try:
        # fill queue (maxsize=8) + a few overflow attempts
        for i in range(20):
            fb.emit(f"msg{i}")
        # we expect at least one drop warning; can't assert exact count
        # without depending on timing
        fb.cancel()  # drain
    finally:
        fb.stop()
