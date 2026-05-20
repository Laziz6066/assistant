# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for voice-assistant.
#
# Build: pyinstaller installer/voice_assistant.spec --noconfirm
# Output: dist/voice-assistant/ (single-folder mode, faster startup vs --onefile)

from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).parent

hiddenimports = [
    # Audio
    "sounddevice",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "pynput._util.win32",
    # ASR
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    # TTS
    "piper",
    "piper.config",
    "onnxruntime",
    # Wake
    "openwakeword",
    "openwakeword.model",
    "openwakeword.utils",
    # System
    "pycaw.pycaw",
    "comtypes.gen",
    "plyer.platforms.win.notification",
    # Tray
    "pystray._win32",
    # LLM
    "ollama",
    # Config
    "pydantic",
    "pydantic_core",
    "yaml",
    "loguru",
    # Project sub-packages (PyInstaller's analysis sometimes misses pure-Python
    # leaf modules that are imported only via dynamic dispatch)
    "voice_assistant.dictation",
    "voice_assistant.nlu",
]

datas = [
    (str(repo_root / "assets"), "assets"),
]

excludes = [
    "pytest", "pytest_cov", "pytest_mock",
    "pyinstaller",
    "torch.distributed", "torch.testing", "torchaudio",
    "IPython", "jupyter", "notebook",
]

a = Analysis(
    [str(repo_root / "src" / "voice_assistant" / "main.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[str(repo_root / "installer" / "runtime_hook.py")],
    excludes=excludes,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="voice-assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(repo_root / "assets" / "tray-icon.png"),
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name="voice-assistant",
)
