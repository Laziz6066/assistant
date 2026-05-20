from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from voice_assistant.activation.models_store import (
    WakeModelStore, WakeModelNotFoundError,
)


def test_init_creates_models_dir(tmp_path):
    target = tmp_path / "wake-models"
    assert not target.exists()
    WakeModelStore(target)
    assert target.is_dir()


def test_ensure_returns_existing_builtin_file(tmp_path):
    store = WakeModelStore(tmp_path)
    # Pre-populate with the alias filename
    fname = WakeModelStore.BUILTIN_ALIASES["hey_jarvis"]
    (tmp_path / fname).write_bytes(b"x" * 1000)
    path = store.ensure("hey_jarvis")
    assert path == tmp_path / fname


def test_ensure_returns_absolute_path_for_custom_onnx(tmp_path):
    custom = tmp_path / "my_wake.onnx"
    custom.write_bytes(b"x" * 100)
    store = WakeModelStore(tmp_path)
    path = store.ensure(str(custom))
    assert path == custom


def test_ensure_unknown_alias_raises(tmp_path):
    store = WakeModelStore(tmp_path)
    with pytest.raises(WakeModelNotFoundError):
        store.ensure("foobar_wake")


def test_ensure_downloads_missing_builtin(tmp_path):
    store = WakeModelStore(tmp_path)
    fname = WakeModelStore.BUILTIN_ALIASES["hey_jarvis"]
    with patch("voice_assistant.activation.models_store.download_models") as dm:
        def _fake_download(model_names, target_directory):
            # Simulate the download producing the file
            Path(target_directory, fname).write_bytes(b"x" * 1000)
        dm.side_effect = _fake_download
        path = store.ensure("hey_jarvis")
    dm.assert_called_once()
    assert path == tmp_path / fname


def test_ensure_download_failure_raises_wake_error(tmp_path):
    store = WakeModelStore(tmp_path)
    with patch("voice_assistant.activation.models_store.download_models") as dm:
        dm.side_effect = RuntimeError("no internet")
        with pytest.raises(WakeModelNotFoundError):
            store.ensure("hey_jarvis")


def test_ensure_download_succeeds_but_file_missing_raises(tmp_path):
    store = WakeModelStore(tmp_path)
    with patch("voice_assistant.activation.models_store.download_models") as dm:
        dm.return_value = None  # download returns but writes no file
        with pytest.raises(WakeModelNotFoundError):
            store.ensure("hey_jarvis")
