# GUI Installer (Portable) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a portable Windows zip distribution (`voice-assistant-0.1.0.zip`) containing a self-contained `voice-assistant.exe` plus user-editable `config/` files. End user unzips, optionally edits `config/default.yaml`, double-clicks the .exe.

**Architecture:** New `paths.py` helper resolves resource and config paths in both dev mode (running from source) and frozen mode (PyInstaller bundle). `installer/` directory holds the PyInstaller spec, runtime hook, build batch script, and end-user README. Existing modules (`main.py`, `ui/tray.py`) switch from hardcoded relative paths to the helper. Most of the verification is manual — the build itself can only be tested by running it.

**Tech Stack:** Python 3.11+, PyInstaller ≥ 6.0 (new dev-only dep), Windows batch script, stdlib `sys`/`pathlib`.

**Depends on:** voice-assistant branch at commit `1b42030` (installer design spec) or later. Spec: `docs/superpowers/specs/2026-05-20-gui-installer-design.md`.

---

## File Structure

**New files:**
- `installer/voice_assistant.spec` — PyInstaller spec
- `installer/runtime_hook.py` — UTF-8 stdio reconfiguration
- `installer/build.bat` — Windows build script
- `installer/README-USER.txt` — 1-page end-user guide shipped in the zip
- `src/voice_assistant/utils/paths.py` — `is_frozen()`, `get_resource_path()`, `get_user_config_dir()`, `get_user_config_path()`
- `tests/unit/utils/test_paths.py` — unit tests for the helper

**Modified files:**
- `src/voice_assistant/main.py` — `_build`/`main` use `paths.get_user_config_path()` and `paths.get_user_config_dir()` for `commands.yaml`
- `src/voice_assistant/ui/tray.py` — `_DEFAULT_ICON_PATH = paths.get_resource_path("assets/tray-icon.png")`
- `pyproject.toml` — add `pyinstaller>=6.0` to the `[project.optional-dependencies] dev` list
- `README.md` — add Build (developer) + Install (end-user) sections + manual checklist additions

No new runtime dependencies. PyInstaller is dev-only.

---

## Task 1: `paths.py` helper

**Files:**
- Create: `src/voice_assistant/utils/paths.py`
- Test: `tests/unit/utils/test_paths.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/utils/test_paths.py
import sys
from pathlib import Path

import pytest

from voice_assistant.utils import paths as paths_mod


@pytest.fixture
def fake_frozen(monkeypatch, tmp_path):
    """Pretend the process is a PyInstaller bundle.

    sys.frozen = True; sys._MEIPASS = tmp_path/_internal (where read-only
    resources live); sys.executable = tmp_path/voice-assistant.exe.
    """
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
    # Must walk up to repo root and include "assets/tray-icon.png" suffix
    assert p.parts[-2:] == ("assets", "tray-icon.png")
    # In dev mode the file must actually exist (repo has it)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/utils/test_paths.py -v`
Expected: 7 FAILs with `ModuleNotFoundError: No module named 'voice_assistant.utils.paths'`.

- [ ] **Step 3: Implement `paths.py`**

Create `src/voice_assistant/utils/paths.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/utils/test_paths.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 7 = 314.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/utils/paths.py tests/unit/utils/test_paths.py
git commit -m "feat(utils): paths helper — frozen-aware resource and config resolution"
```

---

## Task 2: Refactor `ui/tray.py` to use the helper

**Files:**
- Modify: `src/voice_assistant/ui/tray.py`
- Test: extend `tests/unit/ui/test_tray.py`

The existing tray code already has a `Path(__file__).resolve().parent.parent.parent.parent / "assets" / "tray-icon.png"` that the previous review correctly fixed. Switch it to the helper for consistency and to gain frozen-mode support.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/ui/test_tray.py`:

```python
def test_default_icon_path_comes_from_paths_helper():
    """tray._DEFAULT_ICON_PATH must equal paths.get_resource_path(...)."""
    from voice_assistant.ui import tray as tray_mod
    from voice_assistant.utils import paths
    assert tray_mod._DEFAULT_ICON_PATH == paths.get_resource_path(
        "assets/tray-icon.png")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/ui/test_tray.py -v -k default_icon_path_comes_from_paths_helper`
Expected: FAIL — `_DEFAULT_ICON_PATH` still uses the old inline computation.

- [ ] **Step 3: Edit `tray.py`**

Find the existing block at `src/voice_assistant/ui/tray.py:11-16`:

```python
# Resolve the bundled icon relative to the package, not the CWD, so the
# installed assistant finds it regardless of where it's launched from.
# Layout: <repo>/src/voice_assistant/ui/tray.py
#         <repo>/assets/tray-icon.png
_DEFAULT_ICON_PATH = (Path(__file__).resolve().parent.parent.parent.parent
                       / "assets" / "tray-icon.png")
```

Replace with:

```python
from voice_assistant.utils.paths import get_resource_path

# Resolved at import time. Works in both dev (repo-root-relative) and when
# frozen by PyInstaller (sys._MEIPASS-relative).
_DEFAULT_ICON_PATH = get_resource_path("assets/tray-icon.png")
```

(Move the `get_resource_path` import to the top of the file with the other imports.)

- [ ] **Step 4: Run all tray tests to verify regression-free**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/ui/test_tray.py -v`
Expected: all PASS (existing tests preserved, new one green).

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 1 = 315.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/ui/tray.py tests/unit/ui/test_tray.py
git commit -m "refactor(ui): tray uses paths.get_resource_path for the icon"
```

---

## Task 3: Refactor `main.py` to use the helper for config path

**Files:**
- Modify: `src/voice_assistant/main.py`
- Test: extend `tests/unit/test_main.py`

`main.main()` currently hardcodes `config_path = "config/default.yaml"`. We make it use `paths.get_user_config_path()` so that frozen builds find the config alongside the .exe. `_build` also uses the same parent dir to find `commands.yaml`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_main.py`:

```python
def test_main_uses_paths_for_default_config(monkeypatch):
    """main() should call paths.get_user_config_path() rather than passing
    'config/default.yaml' to _build."""
    from voice_assistant import main as main_mod

    captured = {}

    def fake_build(config_path):
        captured["config_path"] = config_path
        raise RuntimeError("stop here — we only care about the arg")

    monkeypatch.setattr(main_mod, "_build", fake_build)

    # Run main(); the RuntimeError unwinds out of fake_build
    try:
        main_mod.main()
    except RuntimeError:
        pass

    expected = main_mod.paths.get_user_config_path()
    assert captured.get("config_path") == str(expected)


def test_build_uses_commands_yaml_in_user_config_dir(tmp_path, monkeypatch):
    """_build derives commands.yaml from the same directory as the config
    path it was given, NOT a hardcoded literal."""
    from voice_assistant import main as main_mod

    monkeypatch.setattr(main_mod, "FasterWhisperEngine", MagicMock())
    monkeypatch.setattr(main_mod, "AudioCapture", MagicMock())
    monkeypatch.setattr(main_mod, "PushToTalk", MagicMock())
    monkeypatch.setattr(main_mod, "VADSegmenter", MagicMock())
    monkeypatch.setattr(main_mod, "register_all", MagicMock())
    monkeypatch.setattr(main_mod, "setup_logging", MagicMock())
    monkeypatch.setattr(main_mod, "SystemTray", MagicMock())

    custom_dir = tmp_path / "weird-loc"
    custom_dir.mkdir()
    (custom_dir / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n"
        "tray:\n  enabled: false\n"
        "dialog:\n  enabled: false\n"
        "dictation:\n  enabled: false\n",
        encoding="utf-8")
    (custom_dir / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")

    pipe, qs, capture, ptt, vad, feedback, tray = main_mod._build(
        str(custom_dir / "default.yaml"))
    # If _build read commands.yaml from the SAME directory as default.yaml,
    # the RulesRouter loaded the 'noop' intent — no exception.
    # If it had a hardcoded path, this test would have errored on missing file.
    assert pipe is not None
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "uses_paths_for_default_config or commands_yaml_in_user_config_dir"`
Expected: 1 FAIL (the first — `main_mod.paths` doesn't exist yet). The second probably passes already since `_build` already takes config_path as a parameter and resolves `commands.yaml` relative to it.

- [ ] **Step 3: Edit `main.py`**

a) At the top of `src/voice_assistant/main.py`, near the other utility imports, add:

```python
from voice_assistant.utils import paths
```

b) Find the `main()` function. Its first line currently is:

```python
def main() -> int:
    config_path = "config/default.yaml"
```

Replace with:

```python
def main() -> int:
    config_path = str(paths.get_user_config_path())
```

c) Verify `_build`'s commands.yaml resolution is already path-derived. The current code looks like:

```python
nlu = RulesRouter(
    commands_path=str(Path(config_path).parent / "commands.yaml"),
    ...
)
```

This is correct — `commands.yaml` is resolved from the parent of whatever config path `_build` received. No change needed.

- [ ] **Step 4: Run new tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "uses_paths_for_default_config or commands_yaml_in_user_config_dir"`
Expected: 2 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 2 = 317.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/main.py tests/unit/test_main.py
git commit -m "refactor(main): main() resolves config path via paths helper"
```

---

## Task 4: Add `pyinstaller` to dev deps

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `pyinstaller>=6.0` to dev extras**

Edit `pyproject.toml`. Find the `[project.optional-dependencies]` section's `dev` list. Append:

```toml
  "pyinstaller>=6.0",
```

If `[project.optional-dependencies]` doesn't exist (deps are in a different layout), look for `dev = [...]` under any tool table; the project added pytest etc. earlier so a `dev` extras list should already exist.

- [ ] **Step 2: Install + smoke check**

```bash
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m PyInstaller --version
```
Expected: PyInstaller prints a version ≥ 6.0.

If install fails (older Python, wheel availability), STOP and report BLOCKED — don't substitute alternatives.

- [ ] **Step 3: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green (no test changes).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): add pyinstaller>=6.0 to dev extras"
```

---

## Task 5: Runtime hook + PyInstaller spec

**Files:**
- Create: `installer/runtime_hook.py`
- Create: `installer/voice_assistant.spec`

These files don't have unit tests of their own — verification is by actually running PyInstaller (Task 7).

- [ ] **Step 1: Create `installer/runtime_hook.py`**

```python
# installer/runtime_hook.py
# Runs before user code. Fixes stdout/stderr encoding so Cyrillic and other
# non-ASCII text doesn't crash the console on Windows code page 1251 / 866.
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

- [ ] **Step 2: Create `installer/voice_assistant.spec`**

```python
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
```

- [ ] **Step 3: Smoke check the spec compiles (parseable by Python)**

```bash
.\.venv\Scripts\python.exe -c "import ast; ast.parse(open('installer/voice_assistant.spec', encoding='utf-8').read())"
```
Expected: no output, exit 0.

The spec uses PyInstaller-only globals (`SPECPATH`, `Analysis`, `PYZ`, `EXE`, `COLLECT`). Running it via `python` directly would NameError on those, which is expected — PyInstaller injects them. The `ast.parse` smoke check confirms syntactic correctness without executing.

- [ ] **Step 4: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green (no changes affecting tests).

- [ ] **Step 5: Commit**

```bash
git add installer/runtime_hook.py installer/voice_assistant.spec
git commit -m "feat(installer): PyInstaller spec + runtime hook for portable build"
```

---

## Task 6: Build script + end-user README

**Files:**
- Create: `installer/build.bat`
- Create: `installer/README-USER.txt`

- [ ] **Step 1: Create `installer/build.bat`**

```batch
@echo off
REM Build voice-assistant portable distribution.
REM Usage: run from anywhere — this script cds to repo root automatically.
setlocal

set REPO_ROOT=%~dp0..
cd /d %REPO_ROOT%

REM Clean previous build artifacts
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller
.venv\Scripts\python.exe -m PyInstaller installer\voice_assistant.spec --noconfirm
if errorlevel 1 (
    echo PyInstaller failed.
    exit /b 1
)

REM Copy user-editable configs alongside the .exe
xcopy /e /i /y config dist\voice-assistant\config\
if errorlevel 1 (
    echo Config copy failed.
    exit /b 1
)
copy /y installer\README-USER.txt dist\voice-assistant\README.txt
if errorlevel 1 (
    echo README copy failed.
    exit /b 1
)

REM Zip the result
.venv\Scripts\python.exe -c "import shutil; shutil.make_archive('dist/voice-assistant-0.1.0', 'zip', 'dist', 'voice-assistant')"
if errorlevel 1 (
    echo Zip step failed.
    exit /b 1
)

echo.
echo Build complete: dist\voice-assistant-0.1.0.zip
echo.
endlocal
```

- [ ] **Step 2: Create `installer/README-USER.txt`**

```text
Voice Assistant — Portable Edition
====================================

QUICK START
  1. Распакуй эту папку куда удобно (например, C:\Apps\voice-assistant\)
  2. Запусти voice-assistant.exe
  3. В трее появится иконка. Зажми Right Ctrl и говори.

CONFIGURATION
  Отредактируй config/default.yaml в текстовом редакторе:
    tts.enabled        — озвучка ответов (требует ~63MB download первый раз)
    llm.enabled        — fallback на ollama (требует установки ollama)
    wake.enabled       — wake word "hey jarvis"
    dictation.enabled  — режим диктовки
    dialog.enabled     — multi-turn

  Команды редактируются в config/commands.yaml (формат — YAML, intent + examples).

UNINSTALL
  Просто удали эту папку. User data в %USERPROFILE%\.voice-assistant\
  (voice models, wake models) останется — удаляй вручную если нужно.

LOGS
  voice_assistant.log создаётся рядом с .exe.

ISSUES
  https://github.com/Laziz6066/assistant/issues
```

- [ ] **Step 3: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green (no test changes).

- [ ] **Step 4: Commit**

```bash
git add installer/build.bat installer/README-USER.txt
git commit -m "feat(installer): build script + end-user README"
```

---

## Task 7: Run the build manually + iterate on missing imports

This task is the only one that exercises the actual PyInstaller build. It is iterative: build, hit a missing-import error, add the module to `hiddenimports`, rebuild. Budget 30-60 minutes the first time on a fresh machine.

The implementer should run the steps below interactively and report DONE_WITH_CONCERNS describing any hidden-import additions or other adjustments needed beyond what Task 5's spec provides.

- [ ] **Step 1: Run the build**

```bash
installer\build.bat
```
Expected: ~3-5 minutes; output ends with `Build complete: dist\voice-assistant-0.1.0.zip`.

If it fails:

- **`ModuleNotFoundError: No module named 'X'`** during PyInstaller's Analysis phase: that import is missing from `hiddenimports`. Add it to `installer/voice_assistant.spec` and rerun.
- **`ImportError` from a `from . import _x` line inside a vendor library**: typically a hidden submodule. Add the full dotted name.
- **PyInstaller crash with "cannot find" for a `.dll` or `.pyd`**: check if a binary needs to go into `binaries` (not `datas`).
- **Disk full / permission denied**: free space / close any process that locked previous `dist/` folder.

If the build succeeds, verify:

```bash
dir dist\voice-assistant\voice-assistant.exe
dir dist\voice-assistant\config\default.yaml
dir dist\voice-assistant\config\commands.yaml
dir dist\voice-assistant\_internal\assets\tray-icon.png
dir dist\voice-assistant-0.1.0.zip
```

- [ ] **Step 2: Smoke-launch the .exe**

```bash
cd dist\voice-assistant
.\voice-assistant.exe
```

Expected within 5 seconds:
- A console window appears with loguru output starting with `loading config from ...`.
- The tray icon appears.
- No traceback in the first 10 seconds.

Press Ctrl+C in the console to stop, or Quit from the tray menu.

If a runtime traceback appears (e.g. `ImportError: cannot import name '_X' from 'Y'`), the missing module is loaded lazily by `Y` at runtime — add it to `hiddenimports` and rebuild from Step 1.

Common offenders we may need to add:
- `pkg_resources.py2_warn` (if any deps use legacy pkg_resources)
- `comtypes.gen.*` modules (pycaw generates these on first run; might need pre-generated)
- `faster_whisper.transcribe` (sometimes split out)

DO NOT skip this manual step — it's the only way to find runtime-only hidden imports.

- [ ] **Step 3: If hiddenimports were added, commit the spec update**

```bash
git add installer/voice_assistant.spec
git commit -m "fix(installer): add discovered hidden imports for X"
```

(If no spec changes were needed, skip this step.)

- [ ] **Step 4: Run unit suite once more to confirm nothing in src/ changed inadvertently**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: same green count as after Task 6 (317).

- [ ] **Step 5: Report**

Implementer reports DONE_WITH_CONCERNS that lists:
- Whether the first build succeeded
- Any hidden imports that needed to be added beyond Task 5's seed list (and committed)
- Size of `dist/voice-assistant-0.1.0.zip`
- Whether the .exe launched and the tray icon appeared
- Any runtime error noted but not fixed (with reproduction steps)

---

## Task 8: README updates + manual checklist

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append Build and Install sections + checklist to `README.md`**

Below the existing "Dictation verification checklist", append:

```markdown

## Build (для разработчика)

Производит portable .zip с .exe и user-editable configs:

```
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
installer\build.bat
```

Результат: `dist/voice-assistant-0.1.0.zip` (~500 MB).

Сборка занимает 3-5 минут. Если падает на missing hidden import — добавь его в `hiddenimports` в `installer/voice_assistant.spec` и пересобери.

## Install (для конечного пользователя)

1. Скачай `voice-assistant-0.1.0.zip` с релизной страницы
2. Распакуй в удобную папку (например, `C:\Apps\voice-assistant\`)
3. Запусти `voice-assistant.exe`
4. Опционально отредактируй `config/default.yaml` чтобы включить TTS / wake / LLM / dictation

User data (voice models, wake models) хранится в `%USERPROFILE%\.voice-assistant\`. Удаление папки приложения её не очищает — удали вручную если нужен полный clean.

## Installer verification checklist

- [ ] `installer\build.bat` завершается без ошибок (~3-5 минут)
- [ ] `dist/voice-assistant-0.1.0.zip` создан, размер ~500 MB
- [ ] Распаковка в чистую папку (без виртуального окружения рядом)
- [ ] Двойной клик по `voice-assistant.exe` — окно консоли + иконка в трее
- [ ] PTT: Right Ctrl → "открой блокнот" → notepad запускается
- [ ] `voice_assistant.log` создаётся рядом с .exe
- [ ] Включить `tts.enabled: true` в `config/default.yaml` → перезапустить → голос качается в `%USERPROFILE%\.voice-assistant\voices\`
- [ ] Tray → Quit → процесс корректно завершается, лог-файл не залочен
- [ ] Удалить папку → нет следов в Program Files / реестре
- [ ] (Опционально) Защитник Windows не флагует .exe как malware
```

- [ ] **Step 2: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green at 317.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: installer build + install + manual checklist"
```

---

## Self-Review Notes

- **Spec coverage:**
  - `paths.py` helper (T1)
  - Tray refactor (T2)
  - main.py refactor (T3)
  - `pyinstaller` dep (T4)
  - PyInstaller spec + runtime hook (T5)
  - Build script + end-user README (T6)
  - Manual build verification (T7)
  - README updates + manual checklist (T8)

  Spec §6 (manual checklist) → Task 8 step 1. Spec §6.1 unit tests → T1 (paths) + T2 (tray) + T3 (main). Spec §6.2 manual-only items → T7.

- **Task ordering:**
  - T1 (`paths.py`) must come before T2 and T3 (they import from it).
  - T4 (`pyinstaller` dep) must come before T5 (we technically can write the spec without it installed, but T7 needs PyInstaller available).
  - T5 must come before T6 (build.bat invokes the spec).
  - T7 is the manual-verification gate before T8 (README documents the build).

- **Type consistency:**
  - `paths.get_resource_path(relative: str) -> Path` used identically in `tray.py`.
  - `paths.get_user_config_path() -> Path` used in `main.main()` as `str(paths.get_user_config_path())`.
  - `paths.is_frozen() -> bool` used inside `paths.py` itself.

- **Test density:** ~10 new tests (7 for paths, 1 for tray helper switch, 2 for main config-path refactor). Manual checklist on top. Expected total after T8: 317 (current 307 + 10).

- **What stays manual** (per spec §6.2): the actual PyInstaller build, .exe launch, antivirus interaction, .zip extraction on another machine. No way around it without a Windows CI runner — out of scope.

- **Risks:**
  - PyInstaller iteration in T7 may surface hidden imports not in T5's seed list. Plan accepts DONE_WITH_CONCERNS for that — controller commits the additions.
  - Defender / SmartScreen warnings on the unsigned .exe are out of our hands. Documented in spec §9 (Future Work).
  - If `pyinstaller>=6.0` doesn't have a wheel for the project's Python version, T4 will BLOCK — escalate then.
