from unittest.mock import patch
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
