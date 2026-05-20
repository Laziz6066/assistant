from voice_assistant.executor.plugins import register_all
from voice_assistant.executor.registry import global_registry


EXPECTED_INTENTS = {
    # apps
    "open_app",
    "close_app",
    # windows
    "minimize_all",
    "close_window",
    "switch_window",
    # browser
    "web_search",
    "open_url",
    "open_bookmark",
    # files
    "open_path",
    # clipboard
    "clipboard_copy",
    "clipboard_paste",
    "clipboard_read",
    # system
    "volume_set",
    "volume_up",
    "volume_down",
    "lock_screen",
    "shutdown",
    "reboot",
    "confirm_yes",
}


def test_register_all_populates_global_registry_with_all_intents():
    register_all()
    reg = global_registry()
    registered = set(reg._handlers.keys())
    missing = EXPECTED_INTENTS - registered
    assert not missing, f"register_all did not register: {missing}"


def test_register_all_is_idempotent():
    # Calling twice should not raise — registry.add overwrites by name.
    register_all()
    register_all()
    reg = global_registry()
    assert "open_app" in reg._handlers
