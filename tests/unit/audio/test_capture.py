import numpy as np
from voice_assistant.audio.capture import RingBuffer


def test_ring_buffer_keeps_last_n_samples():
    rb = RingBuffer(capacity=5)
    rb.extend(np.array([1, 2, 3], dtype=np.int16))
    rb.extend(np.array([4, 5, 6, 7], dtype=np.int16))
    out = rb.snapshot()
    assert list(out) == [3, 4, 5, 6, 7]


def test_ring_buffer_empty_snapshot():
    rb = RingBuffer(capacity=4)
    assert len(rb.snapshot()) == 0


import numpy as np
from voice_assistant.audio.capture import AudioCapture


def test_subscribe_callback_receives_chunk():
    cap = AudioCapture(sample_rate=16000, ring_seconds=1.0, device=None)
    received = []
    cap.subscribe(received.append)
    # Manually invoke the internal callback path with a fake chunk
    chunk = np.zeros(1280, dtype=np.int16)
    indata = chunk.reshape(-1, 1)
    cap._dispatch(indata, frames=1280, time=None, status=None)
    assert len(received) == 1
    assert received[0].shape == (1280,)
    assert received[0].dtype == np.int16


def test_unsubscribe_removes_callback():
    cap = AudioCapture(sample_rate=16000, ring_seconds=1.0, device=None)
    received = []
    cap.subscribe(received.append)
    cap.unsubscribe(received.append)
    chunk = np.zeros(1280, dtype=np.int16)
    cap._dispatch(chunk.reshape(-1, 1), 1280, None, None)
    assert received == []


def test_multiple_subscribers_all_get_chunk():
    cap = AudioCapture(sample_rate=16000, ring_seconds=1.0, device=None)
    a, b = [], []
    cap.subscribe(a.append)
    cap.subscribe(b.append)
    chunk = np.ones(1280, dtype=np.int16) * 5
    cap._dispatch(chunk.reshape(-1, 1), 1280, None, None)
    assert len(a) == 1 and len(b) == 1


def test_subscriber_raising_does_not_block_others():
    cap = AudioCapture(sample_rate=16000, ring_seconds=1.0, device=None)
    def bad(_): raise RuntimeError("boom")
    good_received = []
    cap.subscribe(bad)
    cap.subscribe(good_received.append)
    chunk = np.zeros(1280, dtype=np.int16)
    cap._dispatch(chunk.reshape(-1, 1), 1280, None, None)
    assert len(good_received) == 1


def test_dispatch_still_extends_ring_buffer():
    cap = AudioCapture(sample_rate=16000, ring_seconds=1.0, device=None)
    chunk = np.ones(1600, dtype=np.int16)
    cap._dispatch(chunk.reshape(-1, 1), 1600, None, None)
    snap = cap.ring.snapshot()
    assert len(snap) == 1600
