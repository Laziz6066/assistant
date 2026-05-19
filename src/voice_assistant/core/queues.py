from __future__ import annotations
import queue
from dataclasses import dataclass, field


class _Stop:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<STOP>"


STOP = _Stop()


@dataclass
class PipelineQueues:
    speech_q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
    asr_q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
    nlu_q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
    exec_q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
