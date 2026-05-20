import threading
import time

from voice_assistant.dictation.mode_store import ModeStore


def test_default_state_is_command():
    store = ModeStore()
    assert store.is_command() is True
    assert store.is_dictation() is False
    assert store.current_mode() == "command"


def test_start_dictation_switches_to_dictation():
    store = ModeStore()
    store.start_dictation()
    assert store.is_dictation() is True
    assert store.is_command() is False
    assert store.current_mode() == "dictation"


def test_stop_dictation_switches_back_to_command():
    store = ModeStore()
    store.start_dictation()
    store.stop_dictation()
    assert store.is_command() is True
    assert store.is_dictation() is False


def test_start_dictation_is_idempotent():
    store = ModeStore()
    store.start_dictation()
    store.start_dictation()
    assert store.is_dictation() is True


def test_stop_dictation_is_idempotent():
    store = ModeStore()
    store.stop_dictation()
    store.stop_dictation()
    assert store.is_command() is True


def test_concurrent_toggles_do_not_corrupt_state():
    """Smoke test: two threads toggling don't leave the state in a
    weird in-between value."""
    store = ModeStore()
    stop_evt = threading.Event()

    def toggler():
        while not stop_evt.is_set():
            store.start_dictation()
            store.stop_dictation()

    t1 = threading.Thread(target=toggler, daemon=True)
    t2 = threading.Thread(target=toggler, daemon=True)
    t1.start()
    t2.start()
    time.sleep(0.05)
    stop_evt.set()
    t1.join(timeout=1)
    t2.join(timeout=1)
    # Final state must be a valid string mode
    assert store.current_mode() in ("command", "dictation")
