from __future__ import annotations
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True if running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def get_resource_path(relative: str) -> Path:
    """Resolve a read-only resource bundled with the application.

    - In dev (running from source): repo_root / relative
    - When frozen by PyInstaller: sys._MEIPASS / relative

    `relative` is a forward-slash-separated path like "assets/tray-icon.png".
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS")) / relative
    # paths.py lives at src/voice_assistant/utils/paths.py
    # parents[3] walks: paths.py → utils → voice_assistant → src → <repo>
    return Path(__file__).resolve().parents[3] / relative


def get_user_config_dir() -> Path:
    """Directory containing user-editable config files.

    - In dev: <repo>/config/
    - When frozen: <exe-parent>/config/ (alongside the .exe, NOT in _internal/)
    """
    if is_frozen():
        return Path(sys.executable).parent / "config"
    return Path(__file__).resolve().parents[3] / "config"


def get_user_config_path() -> Path:
    """Full path to the default config YAML."""
    return get_user_config_dir() / "default.yaml"
