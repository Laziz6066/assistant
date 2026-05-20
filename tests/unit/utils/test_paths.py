import sys
from pathlib import Path

import pytest

from voice_assistant.utils import paths as paths_mod


@pytest.fixture
def fake_frozen(monkeypatch, tmp_path):
    """Pretend the process is a PyInstaller bundle."""
    meipass = tmp_path / "_internal"
    meipass.mkdir()
    exe = tmp_path / "voice-assistant.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    return {"meipass": meipass, "exe_parent": tmp_path}


def test_is_frozen_returns_false_in_dev(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths_mod.is_frozen() is False


def test_is_frozen_returns_true_when_sys_frozen_set(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths_mod.is_frozen() is True


def test_get_resource_path_in_dev_resolves_to_repo_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    p = paths_mod.get_resource_path("assets/tray-icon.png")
    assert p.is_absolute()
    assert p.parts[-2:] == ("assets", "tray-icon.png")
    assert p.is_file(), f"expected {p} to exist in dev checkout"


def test_get_resource_path_when_frozen_uses_meipass(fake_frozen):
    p = paths_mod.get_resource_path("assets/tray-icon.png")
    assert p == fake_frozen["meipass"] / "assets" / "tray-icon.png"


def test_get_user_config_dir_in_dev_resolves_to_repo_config(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    d = paths_mod.get_user_config_dir()
    assert d.is_absolute()
    assert d.parts[-1] == "config"
    assert d.is_dir(), f"expected {d} to exist in dev checkout"


def test_get_user_config_dir_when_frozen_is_alongside_exe(fake_frozen):
    d = paths_mod.get_user_config_dir()
    assert d == fake_frozen["exe_parent"] / "config"


def test_get_user_config_path_in_dev_points_at_default_yaml(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    p = paths_mod.get_user_config_path()
    assert p.parts[-2:] == ("config", "default.yaml")
    assert p.is_file()


def test_get_log_path_in_dev_resolves_to_repo_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    p = paths_mod.get_log_path()
    assert p.is_absolute()
    assert p.name == "voice_assistant.log"


def test_get_log_path_when_frozen_is_alongside_exe(fake_frozen):
    p = paths_mod.get_log_path()
    assert p == fake_frozen["exe_parent"] / "voice_assistant.log"
