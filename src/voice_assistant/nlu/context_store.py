from __future__ import annotations
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Deque

from voice_assistant.core.types import Intent


_ENTITY_SLOT_PRIORITY: tuple[str, ...] = ("app", "name", "query", "url")
_SKIP_INTENTS: frozenset[str] = frozenset({"unknown", "confirm_yes"})


class ContextStore:
    """Bounded LRU of recently dispatched intents with TTL expiration.

    Thread-safe: a single Lock guards all mutations and reads.

    Only stores intents that:
      - have at least one string slot in _ENTITY_SLOT_PRIORITY
      - are not "unknown" or "confirm_yes"
    """

    def __init__(self, max_size: int = 5, ttl_s: float = 60.0,
                 clock: Callable[[], float] | None = None) -> None:
        self._buf: Deque[tuple[Intent, float]] = deque(maxlen=max_size)
        self._ttl_s = ttl_s
        self._clock = clock if clock is not None else time.monotonic
        self._lock = threading.Lock()

    def add(self, intent: Intent) -> None:
        if intent.name in _SKIP_INTENTS:
            return
        if not self._has_usable_entity(intent):
            return
        with self._lock:
            self._buf.append((intent, self._clock()))

    def get_recent_entity(self) -> tuple[str, str] | None:
        now = self._clock()
        with self._lock:
            for intent, ts in reversed(self._buf):  # newest first
                if now - ts > self._ttl_s:
                    return None  # newer-first iteration; if this expired,
                                  # everything older is also expired
                for slot_name in _ENTITY_SLOT_PRIORITY:
                    val = intent.slots.get(slot_name)
                    if isinstance(val, str) and val.strip():
                        return (val.strip(), slot_name)
        return None

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    @staticmethod
    def _has_usable_entity(intent: Intent) -> bool:
        for slot_name in _ENTITY_SLOT_PRIORITY:
            val = intent.slots.get(slot_name)
            if isinstance(val, str) and val.strip():
                return True
        return False
