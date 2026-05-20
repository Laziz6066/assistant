from __future__ import annotations
import threading
from collections.abc import Callable
from pathlib import Path
from loguru import logger

import pystray
from PIL import Image, ImageDraw


# Resolve the bundled icon relative to the package, not the CWD, so the
# installed assistant finds it regardless of where it's launched from.
# Layout: <repo>/src/voice_assistant/ui/tray.py
#         <repo>/assets/tray-icon.png
_DEFAULT_ICON_PATH = (Path(__file__).resolve().parent.parent.parent.parent
                       / "assets" / "tray-icon.png")
_STOP_JOIN_TIMEOUT_S = 2.0


def _load_icon(icon_path: Path | None) -> Image.Image:
    """Load the tray icon image from disk, or fall back to a programmatic
    placeholder (blue circle with 'VA' text) if the file is missing.
    """
    if icon_path is not None and icon_path.is_file():
        return Image.open(icon_path)
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(30, 120, 220, 255))
    draw.text((18, 22), "VA", fill="white")
    return img


class SystemTray:
    """Persistent system-tray icon with right-click menu.

    Lifecycle:
      __init__(quit_callback, version, icon_path) — builds the
        pystray.Icon object; does NOT spawn threads.
      start() — spawns a daemon thread that runs Icon.run(); returns
        immediately.
      stop()  — calls Icon.stop() so the daemon thread exits; joins
        with 2s timeout. Idempotent.
    """

    def __init__(self, quit_callback: Callable[[], None],
                 version: str = "0.1.0",
                 icon_path: Path | None = None) -> None:
        self._quit_callback = quit_callback
        self._version = version
        self._thread: threading.Thread | None = None
        self._stopped = False

        image = _load_icon(icon_path
                            if icon_path is not None
                            else _DEFAULT_ICON_PATH)

        menu = pystray.Menu(
            pystray.MenuItem("About", self._on_about),
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(
            "voice-assistant",
            image,
            "Voice Assistant",
            menu,
        )

    def set_quit_callback(self, callback: Callable[[], None]) -> None:
        """Replace the quit callback. Useful when the real callback isn't
        available at construction time (e.g. it captures objects created
        later in main())."""
        self._quit_callback = callback

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run_safely, daemon=True, name="SystemTray.run")
        self._thread.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        try:
            self._icon.stop()
        except Exception:
            logger.exception("tray icon.stop() failed")
        if self._thread is not None:
            self._thread.join(timeout=_STOP_JOIN_TIMEOUT_S)

    def _run_safely(self) -> None:
        try:
            self._icon.run()
        except Exception:
            logger.exception("tray Icon.run failed on daemon thread")

    def _on_quit(self, icon, item) -> None:
        try:
            self._quit_callback()
        except Exception:
            logger.exception("tray quit_callback raised")
        try:
            self._icon.stop()
        except Exception:
            logger.exception("tray Icon.stop after quit failed")

    def _on_about(self, icon, item) -> None:
        logger.info(f"Voice Assistant {self._version}")
