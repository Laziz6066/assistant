from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from voice_assistant.feedback.voice_models import (
    VoiceModelStore, VoiceDownloadError,
)


def _make_fake_files(voices_dir: Path, voice: str, onnx_size: int = 2_000_000):
    voices_dir.mkdir(parents=True, exist_ok=True)
    (voices_dir / f"{voice}.onnx").write_bytes(b"x" * onnx_size)
    (voices_dir / f"{voice}.onnx.json").write_text('{"sample_rate":22050}',
                                                    encoding="utf-8")


def test_is_present_true_when_both_files_exist_and_onnx_large_enough(tmp_path):
    _make_fake_files(tmp_path, "ru_RU-irina-medium")
    store = VoiceModelStore(tmp_path)
    assert store.is_present("ru_RU-irina-medium") is True


def test_is_present_false_when_json_missing(tmp_path):
    (tmp_path / "ru_RU-irina-medium.onnx").write_bytes(b"x" * 2_000_000)
    store = VoiceModelStore(tmp_path)
    assert store.is_present("ru_RU-irina-medium") is False


def test_is_present_false_when_onnx_too_small(tmp_path):
    _make_fake_files(tmp_path, "ru_RU-irina-medium", onnx_size=500)
    store = VoiceModelStore(tmp_path)
    assert store.is_present("ru_RU-irina-medium") is False


def test_url_for_parses_voice_name():
    store = VoiceModelStore(Path("/tmp/voices"))
    onnx, jsn = store._url_for("ru_RU-irina-medium")
    assert "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx" in onnx
    assert "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json" in jsn


def test_url_for_invalid_voice_name_raises():
    store = VoiceModelStore(Path("/tmp/voices"))
    with pytest.raises(VoiceDownloadError):
        store._url_for("bad-name")


def test_ensure_skips_download_when_already_present(tmp_path):
    _make_fake_files(tmp_path, "ru_RU-irina-medium")
    with patch("voice_assistant.feedback.voice_models.requests.get") as gmock:
        store = VoiceModelStore(tmp_path)
        onnx, jsn = store.ensure("ru_RU-irina-medium")
    gmock.assert_not_called()
    assert onnx.exists() and jsn.exists()


def _fake_response(content_chunks, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if status >= 400:
        from requests import HTTPError
        resp.raise_for_status.side_effect = HTTPError(f"status {status}")
    resp.iter_content = MagicMock(return_value=iter(content_chunks))
    resp.headers = {"content-length": str(sum(len(c) for c in content_chunks))}
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=None)
    return resp


def test_ensure_downloads_atomically(tmp_path):
    big_chunk = b"x" * 2_000_000
    json_bytes = b'{"sample_rate":22050}'
    with patch("voice_assistant.feedback.voice_models.requests.get") as gmock:
        gmock.side_effect = [
            _fake_response([big_chunk]),         # .onnx
            _fake_response([json_bytes]),        # .onnx.json
        ]
        store = VoiceModelStore(tmp_path)
        onnx, jsn = store.ensure("ru_RU-irina-medium")
    assert onnx.exists()
    assert onnx.read_bytes() == big_chunk
    assert jsn.read_text(encoding="utf-8") == json_bytes.decode()
    # .tmp/ should be empty after success
    tmp_dir = tmp_path / ".tmp"
    assert not list(tmp_dir.iterdir())


def test_ensure_raises_on_404(tmp_path):
    with patch("voice_assistant.feedback.voice_models.requests.get") as gmock:
        gmock.return_value = _fake_response([b""], status=404)
        store = VoiceModelStore(tmp_path)
        with pytest.raises(VoiceDownloadError):
            store.ensure("ru_RU-irina-medium")


def test_ensure_raises_on_network_error(tmp_path):
    import requests
    with patch("voice_assistant.feedback.voice_models.requests.get") as gmock:
        gmock.side_effect = requests.ConnectionError("no internet")
        store = VoiceModelStore(tmp_path)
        with pytest.raises(VoiceDownloadError):
            store.ensure("ru_RU-irina-medium")


def test_init_cleans_stale_tmp(tmp_path):
    stale = tmp_path / ".tmp"
    stale.mkdir(parents=True)
    (stale / "garbage.part").write_bytes(b"x" * 1000)
    store = VoiceModelStore(tmp_path)
    assert not list(stale.iterdir())
