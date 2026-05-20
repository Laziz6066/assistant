import time
import threading
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from voice_assistant.ui.tray import SystemTray


def _make_quit_cb():
    return MagicMock()


def test_init_constructs_icon_with_menu():
    quit_cb = _make_quit_cb()
    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu") as MockMenu, \
         patch("voice_assistant.ui.tray.pystray.MenuItem") as MockMenuItem, \
         patch("voice_assistant.ui.tray._load_icon") as MockLoadIcon:
        MockLoadIcon.return_value = MagicMock(name="image")
        tray = SystemTray(quit_callback=quit_cb, version="0.2.0")
    # Icon was constructed
    MockIcon.assert_called_once()
    # Two menu items: About and Quit
    assert MockMenuItem.call_count == 2
    menu_texts = [call.args[0] for call in MockMenuItem.call_args_list]
    assert "About" in menu_texts
    assert "Quit" in menu_texts


def test_start_spawns_daemon_thread_and_runs_icon():
    quit_cb = _make_quit_cb()
    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem"), \
         patch("voice_assistant.ui.tray._load_icon"):
        # Icon.run blocks until Icon.stop is called; simulate with an Event
        run_event = threading.Event()
        inst = MagicMock()
        inst.run = MagicMock(side_effect=lambda: run_event.wait(timeout=2))
        inst.stop = MagicMock(side_effect=lambda: run_event.set())
        MockIcon.return_value = inst

        tray = SystemTray(quit_callback=quit_cb)
        tray.start()
        time.sleep(0.05)
        assert tray._thread is not None
        assert tray._thread.is_alive()
        assert tray._thread.daemon is True
        inst.run.assert_called()

        tray.stop()
        time.sleep(0.05)
        assert not tray._thread.is_alive()


def test_stop_calls_icon_stop_and_joins():
    quit_cb = _make_quit_cb()
    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem"), \
         patch("voice_assistant.ui.tray._load_icon"):
        run_event = threading.Event()
        inst = MagicMock()
        inst.run = MagicMock(side_effect=lambda: run_event.wait(timeout=2))
        inst.stop = MagicMock(side_effect=lambda: run_event.set())
        MockIcon.return_value = inst

        tray = SystemTray(quit_callback=quit_cb)
        tray.start()
        time.sleep(0.05)
        tray.stop()
        inst.stop.assert_called_once()


def test_stop_is_idempotent():
    quit_cb = _make_quit_cb()
    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem"), \
         patch("voice_assistant.ui.tray._load_icon"):
        inst = MagicMock()
        MockIcon.return_value = inst
        tray = SystemTray(quit_callback=quit_cb)
        tray.stop()
        tray.stop()


def test_quit_menu_invokes_callback_and_stops_icon():
    quit_cb = _make_quit_cb()
    captured = {}

    def capture_menu_items(*args, **kwargs):
        text = args[0]
        action = args[1] if len(args) > 1 else None
        captured[text] = action
        return MagicMock(name=f"item_{text}")

    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem",
                side_effect=capture_menu_items), \
         patch("voice_assistant.ui.tray._load_icon"):
        inst = MagicMock()
        MockIcon.return_value = inst
        tray = SystemTray(quit_callback=quit_cb)
        quit_action = captured["Quit"]
        assert quit_action is not None
        quit_action(inst, MagicMock())
        quit_cb.assert_called_once()
        inst.stop.assert_called_once()


def test_about_menu_does_not_invoke_quit_callback():
    quit_cb = _make_quit_cb()
    captured = {}

    def capture_menu_items(*args, **kwargs):
        text = args[0]
        action = args[1] if len(args) > 1 else None
        captured[text] = action
        return MagicMock(name=f"item_{text}")

    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem",
                side_effect=capture_menu_items), \
         patch("voice_assistant.ui.tray._load_icon"):
        inst = MagicMock()
        MockIcon.return_value = inst
        tray = SystemTray(quit_callback=quit_cb, version="9.9.9")
        about_action = captured["About"]
        about_action(inst, MagicMock())
        quit_cb.assert_not_called()


def test_load_icon_uses_path_when_exists(tmp_path):
    from voice_assistant.ui.tray import _load_icon
    from PIL import Image
    p = tmp_path / "icon.png"
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(p)
    img = _load_icon(p)
    assert img.size == (16, 16)


def test_load_icon_fallback_when_path_missing(tmp_path):
    from voice_assistant.ui.tray import _load_icon
    img = _load_icon(None)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"
    img2 = _load_icon(tmp_path / "missing.png")
    assert img2.size == (64, 64)


def test_quit_callback_raising_still_calls_icon_stop():
    quit_cb = MagicMock(side_effect=RuntimeError("boom"))
    captured = {}

    def capture_menu_items(*args, **kwargs):
        text = args[0]
        action = args[1] if len(args) > 1 else None
        captured[text] = action
        return MagicMock()

    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem",
                side_effect=capture_menu_items), \
         patch("voice_assistant.ui.tray._load_icon"):
        inst = MagicMock()
        MockIcon.return_value = inst
        tray = SystemTray(quit_callback=quit_cb)
        quit_action = captured["Quit"]
        quit_action(inst, MagicMock())
        inst.stop.assert_called_once()


def test_default_icon_path_is_absolute_and_points_at_assets():
    """The default icon path must be absolute (not CWD-relative) so the
    bundled PNG is found regardless of the user's working directory."""
    from voice_assistant.ui.tray import _DEFAULT_ICON_PATH
    assert _DEFAULT_ICON_PATH.is_absolute()
    assert _DEFAULT_ICON_PATH.parts[-2:] == ("assets", "tray-icon.png")
