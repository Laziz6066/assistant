from __future__ import annotations
import os
import platform
import subprocess
from pathlib import Path

from loguru import logger


def _make_keyboard_controller():
    """Lazy import of pynput.keyboard.Controller; isolated as a function
    so tests can patch it without importing pynput in the test session."""
    from pynput.keyboard import Controller
    return Controller()


class PlatformOps:
    """Windows implementation. Linux/macOS deferred to Release stage."""

    def _spawn(self, cmd: str) -> None:
        subprocess.Popen(cmd, shell=True)

    def _open(self, path: str) -> None:
        os.startfile(path)  # type: ignore[attr-defined]

    def launch_app(self, name: str) -> None:
        self._spawn(name)

    def close_app(self, name: str) -> None:
        subprocess.run(["taskkill", "/IM", f"{name}.exe", "/F"],
                        capture_output=True, check=False)

    def open_path(self, path: str) -> None:
        self._open(str(Path(os.path.expanduser(path))))

    def set_volume(self, percent: int) -> None:
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(max(0, min(100, percent)) / 100.0, None)

    def lock_screen(self) -> None:
        self._spawn("rundll32.exe user32.dll,LockWorkStation")

    def shutdown(self, reboot: bool = False) -> None:
        flag = "/r" if reboot else "/s"
        self._spawn(f"shutdown {flag} /t 0")

    def type_text(self, text: str) -> None:
        if not text:
            return
        ctrl = _make_keyboard_controller()
        ctrl.type(text)


def get_platform_ops() -> PlatformOps:
    if platform.system() != "Windows":
        raise NotImplementedError("Only Windows is supported in MVP")
    return PlatformOps()
