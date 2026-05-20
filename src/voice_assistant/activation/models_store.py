from __future__ import annotations
from pathlib import Path
from loguru import logger

from openwakeword.utils import download_models


class WakeModelNotFoundError(Exception):
    """Raised when a wake model can't be located locally and can't be downloaded."""


class WakeModelStore:
    """Resolve a wake-word model name to a local .onnx file.

    Built-in aliases use openWakeWord's bundled downloader. Custom models
    are accepted as absolute filesystem paths to a .onnx file.
    """

    BUILTIN_ALIASES = {
        "hey_jarvis":  "hey_jarvis_v0.1.onnx",
        "alexa":       "alexa_v0.1.onnx",
        "computer":    "computer_v0.1.onnx",
        "hey_mycroft": "hey_mycroft_v0.1.onnx",
    }

    def __init__(self, models_dir: Path | str):
        self._dir = Path(models_dir).expanduser()
        self._dir.mkdir(parents=True, exist_ok=True)

    def ensure(self, model: str) -> Path:
        # 1. Absolute path to .onnx provided directly
        p = Path(model)
        if p.suffix == ".onnx" and p.is_file():
            return p
        # 2. Built-in alias
        if model in self.BUILTIN_ALIASES:
            target = self._dir / self.BUILTIN_ALIASES[model]
            if not target.is_file():
                self._download_builtin(model)
            if not target.is_file():
                raise WakeModelNotFoundError(
                    f"download finished but {target.name} not found in "
                    f"{self._dir}")
            return target
        raise WakeModelNotFoundError(
            f"unknown wake-word model: {model!r} "
            f"(aliases: {list(self.BUILTIN_ALIASES)})")

    def _download_builtin(self, alias: str) -> None:
        logger.info(
            f"Downloading wake-word model {alias!r} into {self._dir}...")
        try:
            download_models(model_names=[alias],
                             target_directory=str(self._dir))
        except Exception as e:
            raise WakeModelNotFoundError(
                f"failed to download {alias}: {e}") from e
