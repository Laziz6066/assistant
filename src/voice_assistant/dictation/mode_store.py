from __future__ import annotations
import threading


class ModeStore:
    """Thread-safe state machine for assistant operating mode.

    Modes:
      "command"   — default. Pipeline dispatches intents normally.
      "dictation" — Pipeline routes transcripts to DictationProcessor.

    All transitions are idempotent.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode = "command"

    def is_dictation(self) -> bool:
        with self._lock:
            return self._mode == "dictation"

    def is_command(self) -> bool:
        with self._lock:
            return self._mode == "command"

    def start_dictation(self) -> None:
        with self._lock:
            self._mode = "dictation"

    def stop_dictation(self) -> None:
        with self._lock:
            self._mode = "command"

    def current_mode(self) -> str:
        with self._lock:
            return self._mode
