from __future__ import annotations
from typing import Callable
from loguru import logger
from voice_assistant.activation.base import Activator


class PushToTalk(Activator):
    def __init__(self, key_name: str, on_state_change: Callable[[bool], None]):
        self.key_name = key_name
        self._on_state_change = on_state_change
        self._held = False
        self._listener = None

    def _on_press_key(self) -> None:
        if self._held:
            return
        self._held = True
        self._on_state_change(True)

    def _on_release_key(self) -> None:
        if not self._held:
            return
        self._held = False
        self._on_state_change(False)

    def start(self) -> None:
        from pynput import keyboard

        target = getattr(keyboard.Key, self.key_name, None)
        if target is None:
            raise ValueError(f"Unknown hotkey: {self.key_name}")

        def on_press(key):
            if key == target:
                self._on_press_key()

        def on_release(key):
            if key == target:
                self._on_release_key()

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()
        logger.info(f"push-to-talk armed on {self.key_name}")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
