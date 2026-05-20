from unittest.mock import patch, MagicMock
from voice_assistant.utils.platform import PlatformOps, get_platform_ops


def test_get_platform_ops_returns_instance():
    ops = get_platform_ops()
    assert isinstance(ops, PlatformOps)


def test_launch_app_calls_subprocess(monkeypatch):
    ops = get_platform_ops()
    called = {}
    monkeypatch.setattr(ops, "_spawn", lambda cmd: called.setdefault("cmd", cmd))
    ops.launch_app("notepad")
    assert called["cmd"] == "notepad"


def test_open_path_expands_user(monkeypatch):
    ops = get_platform_ops()
    seen = {}
    monkeypatch.setattr(ops, "_open", lambda p: seen.setdefault("p", p))
    ops.open_path("~")
    assert "~" not in seen["p"]


def test_type_text_calls_pynput_controller():
    from voice_assistant.utils.platform import PlatformOps
    ops = PlatformOps()
    with patch("voice_assistant.utils.platform._make_keyboard_controller") as mk:
        ctrl = MagicMock()
        mk.return_value = ctrl
        ops.type_text("hello")
        ctrl.type.assert_called_once_with("hello")


def test_type_text_empty_is_noop():
    from voice_assistant.utils.platform import PlatformOps
    ops = PlatformOps()
    with patch("voice_assistant.utils.platform._make_keyboard_controller") as mk:
        ops.type_text("")
        mk.assert_not_called()


def test_type_text_unicode_passes_through():
    from voice_assistant.utils.platform import PlatformOps
    ops = PlatformOps()
    with patch("voice_assistant.utils.platform._make_keyboard_controller") as mk:
        ctrl = MagicMock()
        mk.return_value = ctrl
        ops.type_text("привет — Hello.")
        ctrl.type.assert_called_once_with("привет — Hello.")


def test_type_text_controller_exception_propagates():
    """type_text should raise on pynput failure; DictationProcessor catches
    upstream."""
    from voice_assistant.utils.platform import PlatformOps
    ops = PlatformOps()
    with patch("voice_assistant.utils.platform._make_keyboard_controller") as mk:
        ctrl = MagicMock()
        ctrl.type.side_effect = RuntimeError("no keyboard")
        mk.return_value = ctrl
        try:
            ops.type_text("hi")
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError to propagate")
