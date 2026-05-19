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
