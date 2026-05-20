from __future__ import annotations
import os
import re
from pathlib import Path

import requests
from loguru import logger

_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
_MIN_ONNX_SIZE = 1_000_000  # 1 MB sanity check
_VOICE_NAME_RE = re.compile(r"^([a-z]{2})_([A-Z]{2})-([a-z]+)-([a-z]+)$")
_DOWNLOAD_TIMEOUT_S = 30
_PROGRESS_LOG_EVERY_BYTES = 10 * 1024 * 1024


class VoiceDownloadError(Exception):
    """Raised when a voice model can't be located locally and can't be
    downloaded."""


class VoiceModelStore:
    def __init__(self, voices_dir: Path) -> None:
        self._dir = Path(voices_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._tmp = self._dir / ".tmp"
        self._tmp.mkdir(exist_ok=True)
        self._clean_tmp()

    def _clean_tmp(self) -> None:
        for f in self._tmp.iterdir():
            try:
                f.unlink()
            except OSError as e:
                logger.warning(f"could not remove stale tmp file {f}: {e}")

    def is_present(self, voice: str) -> bool:
        onnx = self._dir / f"{voice}.onnx"
        jsn = self._dir / f"{voice}.onnx.json"
        if not onnx.exists() or not jsn.exists():
            return False
        try:
            return onnx.stat().st_size >= _MIN_ONNX_SIZE
        except OSError:
            return False

    def _url_for(self, voice: str) -> tuple[str, str]:
        m = _VOICE_NAME_RE.match(voice)
        if not m:
            raise VoiceDownloadError(
                f"voice name '{voice}' does not match "
                f"<lang>_<COUNTRY>-<speaker>-<quality>"
            )
        lang, country, speaker, quality = m.groups()
        lang_country = f"{lang}_{country}"
        base = f"{_HF_BASE}/{lang}/{lang_country}/{speaker}/{quality}/{voice}"
        return f"{base}.onnx", f"{base}.onnx.json"

    def ensure(self, voice: str) -> tuple[Path, Path]:
        onnx = self._dir / f"{voice}.onnx"
        jsn = self._dir / f"{voice}.onnx.json"
        if self.is_present(voice):
            return onnx, jsn
        onnx_url, jsn_url = self._url_for(voice)
        logger.info(f"Downloading voice model {voice} (~63 MB)...")
        try:
            self._download(onnx_url, onnx)
            self._download(jsn_url, jsn)
        except VoiceDownloadError:
            raise
        except requests.RequestException as e:
            raise VoiceDownloadError(f"download failed: {e}") from e
        except OSError as e:
            raise VoiceDownloadError(f"disk write failed: {e}") from e
        return onnx, jsn

    def _download(self, url: str, dest: Path) -> None:
        part = self._tmp / (dest.name + ".part")
        try:
            with requests.get(url, stream=True,
                              timeout=_DOWNLOAD_TIMEOUT_S) as resp:
                if resp.status_code == 404:
                    raise VoiceDownloadError(f"not found: {url}")
                resp.raise_for_status()
                bytes_written = 0
                next_log_at = _PROGRESS_LOG_EVERY_BYTES
                with part.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        bytes_written += len(chunk)
                        if bytes_written >= next_log_at:
                            mb = bytes_written // (1024 * 1024)
                            logger.info(f"  downloaded {mb} MB...")
                            next_log_at += _PROGRESS_LOG_EVERY_BYTES
            os.replace(part, dest)
        finally:
            if part.exists():
                try:
                    part.unlink()
                except OSError:
                    pass
