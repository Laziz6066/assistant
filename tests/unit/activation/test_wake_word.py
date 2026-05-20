import threading
import time
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from voice_assistant.activation.wake_word import WakeWordActivator
from voice_assistant.activation.models_store import (
    WakeModelStore, WakeModelNotFoundError,
)


# Each "chunk" represents ~80ms of 16kHz mono audio (1280 samples).
_CHUNK_SAMPLES = 1280
_LOUD = np.ones(_CHUNK_SAMPLES, dtype=np.int16) * 5000
_SILENT = np.zeros(_CHUNK_SAMPLES, dtype=np.int16)


class _FakeActivator(WakeWordActivator):
    """Test subclass: predict() is scripted; _load_engine is no-op."""

    def __init__(self, *args, scores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._scripted_scores = list(scores or [])
        self._reset_calls = 0

    def _load_engine(self, onnx_path):
        pass

    def _predict_score(self, chunk):
        if self._scripted_scores:
            return self._scripted_scores.pop(0)
        return 0.0

    def _reset_engine(self):
        self._reset_calls += 1


def _make_capture_mock():
    cap = MagicMock()
    cap.subscribe = MagicMock()
    cap.unsubscribe = MagicMock()
    return cap


def _make_store_mock(tmp_path):
    store = MagicMock()
    store.ensure.return_value = tmp_path / "fake.onnx"
    return store


def _drain(activator, timeout=1.0):
    """Wait until the activator's audio queue is empty."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if activator._audio_q.empty():
            time.sleep(0.05)  # let worker process the last item
            if activator._audio_q.empty():
                return
        time.sleep(0.01)


def test_start_subscribes_and_marks_available(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    fa = _FakeActivator(model="hey_jarvis", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state)
    fa.start()
    try:
        assert fa._available is True
        cap.subscribe.assert_called_once_with(fa._on_audio_chunk)
    finally:
        fa.stop()


def test_start_failure_keeps_unavailable(tmp_path):
    cap = _make_capture_mock()
    store = MagicMock()
    store.ensure.side_effect = WakeModelNotFoundError("no internet")
    on_state = MagicMock()
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state)
    fa.start()
    try:
        assert fa._available is False
        cap.subscribe.assert_not_called()
    finally:
        fa.stop()


def test_idle_low_score_no_transition(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state, scores=[0.1, 0.2, 0.3])
    fa.start()
    try:
        for _ in range(3):
            fa._on_audio_chunk(_LOUD)
        _drain(fa)
        on_state.assert_not_called()
        assert fa._state == "IDLE"
    finally:
        fa.stop()


def test_high_score_transitions_to_collecting(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state, scores=[0.9])
    fa.start()
    try:
        fa._on_audio_chunk(_LOUD)
        _drain(fa)
        on_state.assert_called_once_with(True)
        assert fa._state == "COLLECTING"
    finally:
        fa.stop()


def test_collecting_silence_triggers_release(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    # First chunk fires wake, then 10 silent chunks (~800ms) → release
    scores = [0.9] + [0.0] * 10
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state, scores=scores,
                         _sample_rate=16000)
    fa.start()
    try:
        fa._on_audio_chunk(_LOUD)         # wake
        for _ in range(10):
            fa._on_audio_chunk(_SILENT)   # 10 * 80ms = 800ms silence
        _drain(fa)
        # Should see (True) then (False)
        calls = [c.args[0] for c in on_state.call_args_list]
        assert calls == [True, False]
        assert fa._state == "IDLE"
    finally:
        fa.stop()


def test_collecting_max_speech_triggers_release(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    # Wake then 130 loud chunks (~10.4s) → max ceiling at 10s
    scores = [0.9] + [0.0] * 130
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state, scores=scores,
                         _sample_rate=16000)
    fa.start()
    try:
        fa._on_audio_chunk(_LOUD)
        for _ in range(130):
            fa._on_audio_chunk(_LOUD)
        _drain(fa)
        calls = [c.args[0] for c in on_state.call_args_list]
        # At least one True and one False
        assert True in calls
        assert False in calls
    finally:
        fa.stop()


def test_collecting_ignores_subsequent_wake(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    # Wake, then another would-be-wake while still COLLECTING, then silence
    scores = [0.9, 0.95] + [0.0] * 10
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state, scores=scores,
                         _sample_rate=16000)
    fa.start()
    try:
        for _ in range(12):
            fa._on_audio_chunk(_LOUD)
        _drain(fa)
        calls = [c.args[0] for c in on_state.call_args_list]
        # Exactly one True and one False — second 0.95 doesn't re-fire
        assert calls.count(True) == 1
        assert calls.count(False) == 1
    finally:
        fa.stop()


def test_predict_exception_keeps_worker_alive(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state)
    # Replace predict to raise on first call, return 0.9 on second
    calls = [0]
    def predict(_chunk):
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("model boom")
        return 0.9
    fa._predict_score = predict
    fa.start()
    try:
        fa._on_audio_chunk(_LOUD)
        fa._on_audio_chunk(_LOUD)
        _drain(fa)
        on_state.assert_called_with(True)
    finally:
        fa.stop()


def test_queue_overflow_drops_silently(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state)
    fa.start()
    try:
        # _on_audio_chunk must NEVER raise, regardless of queue state
        # Fill queue with junk to simulate slow worker
        for _ in range(100):
            fa._on_audio_chunk(_LOUD)
        # No exception means PASS
    finally:
        fa.stop()


def test_stop_joins_thread_and_unsubscribes(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state)
    fa.start()
    assert fa._thread is not None and fa._thread.is_alive()
    fa.stop()
    cap.unsubscribe.assert_called_once_with(fa._on_audio_chunk)
    assert not fa._thread.is_alive()


def test_reset_engine_called_on_collecting_to_idle(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    # Wake then silence
    scores = [0.9] + [0.0] * 10
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state, scores=scores,
                         _sample_rate=16000)
    fa.start()
    try:
        fa._on_audio_chunk(_LOUD)
        for _ in range(10):
            fa._on_audio_chunk(_SILENT)
        _drain(fa)
        # _reset_engine should have been called exactly once at the
        # COLLECTING → IDLE transition
        assert fa._reset_calls == 1
    finally:
        fa.stop()


def test_stop_when_unavailable_is_safe(tmp_path):
    cap = _make_capture_mock()
    store = MagicMock()
    store.ensure.side_effect = WakeModelNotFoundError("nope")
    on_state = MagicMock()
    fa = _FakeActivator(model="x", store=store, capture=cap,
                         threshold=0.5, silence_ms=800, max_speech_ms=10000,
                         on_state_change=on_state)
    fa.start()
    # _available is False; stop() must not raise and must not unsubscribe
    fa.stop()
    cap.unsubscribe.assert_not_called()


def test_load_engine_calls_real_model_load(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    (tmp_path / "fake.onnx").write_bytes(b"x" * 1000)
    with patch("voice_assistant.activation.wake_word.Model") as MockModel:
        inst = MagicMock()
        inst.predict.return_value = {"hey_jarvis": 0.05}
        MockModel.return_value = inst
        # Use the real WakeWordActivator (not the test subclass)
        fa = WakeWordActivator(model="hey_jarvis", store=store,
                                capture=cap, threshold=0.5,
                                silence_ms=800, max_speech_ms=10000,
                                on_state_change=on_state)
        fa.start()
        try:
            MockModel.assert_called_once()
            assert fa._available is True
        finally:
            fa.stop()


def test_predict_score_uses_model_predict(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    (tmp_path / "fake.onnx").write_bytes(b"x" * 1000)
    with patch("voice_assistant.activation.wake_word.Model") as MockModel:
        inst = MagicMock()
        inst.predict.return_value = {"hey_jarvis": 0.92}
        MockModel.return_value = inst
        fa = WakeWordActivator(model="hey_jarvis", store=store,
                                capture=cap, threshold=0.5,
                                silence_ms=800, max_speech_ms=10000,
                                on_state_change=on_state)
        fa.start()
        try:
            fa._on_audio_chunk(_LOUD)
            _drain(fa)
            on_state.assert_called_once_with(True)
        finally:
            fa.stop()


def test_reset_engine_calls_real_reset(tmp_path):
    cap = _make_capture_mock()
    store = _make_store_mock(tmp_path)
    on_state = MagicMock()
    (tmp_path / "fake.onnx").write_bytes(b"x" * 1000)
    with patch("voice_assistant.activation.wake_word.Model") as MockModel:
        inst = MagicMock()
        # First call (probe in _load_engine): sets _model_key.
        # Second call: triggers wake. Then 10 silent chunks → reset.
        scores = ([{"hey_jarvis": 0.0}]      # probe
                  + [{"hey_jarvis": 0.92}]   # wake
                  + [{"hey_jarvis": 0.0}] * 10)  # silence → release
        inst.predict.side_effect = scores
        MockModel.return_value = inst
        fa = WakeWordActivator(model="hey_jarvis", store=store,
                                capture=cap, threshold=0.5,
                                silence_ms=800, max_speech_ms=10000,
                                on_state_change=on_state,
                                _sample_rate=16000)
        fa.start()
        try:
            fa._on_audio_chunk(_LOUD)
            for _ in range(10):
                fa._on_audio_chunk(_SILENT)
            _drain(fa)
            # The mocked Model received a reset call exactly once
            assert (inst.reset_prediction_buffer.called
                    or inst.reset.called), "expected reset method to be called"
        finally:
            fa.stop()
