# GUI Installer (Portable) — Design Spec

**Date:** 2026-05-20
**Status:** Approved, ready for implementation plan
**Sub-project:** Beta (final feature, post-MVP + Piper TTS + ollama + wake + tray + multi-turn + dictation)
**Depends on:** voice-assistant branch at commit `e4ac220` or later

## 1. Goal

Produce a portable Windows distribution: a `voice-assistant-0.1.0.zip` containing a self-contained `voice-assistant.exe` plus user-editable `config/` files. End user unzips, edits config if needed, double-clicks the .exe — no Python install, no pip, no terminal.

## 2. Scope

**In:**
- PyInstaller `.spec` (single-folder mode, `console=True` for log visibility)
- `runtime_hook.py` for UTF-8 stdout/stderr on Windows console
- `build.bat` build script that produces `dist/voice-assistant-0.1.0.zip`
- `paths.py` helper that resolves resource and config paths in both dev and frozen modes
- Pipeline / tray refactor to call `paths.*` instead of hardcoded relative strings
- 1-page end-user README shipped in the zip
- Build & install sections in the main `README.md`
- Unit tests for `paths.py` (frozen-mode detection mocked via `sys.frozen` and `sys._MEIPASS`)

**Out (deferred):**
- Inno Setup / NSIS wizard installer (Next-Next-Finish UI, Start Menu shortcuts, autostart)
- MSI via WiX (enterprise-grade)
- Code signing (Authenticode)
- Auto-update mechanism
- First-run wizard (Qt/tkinter GUI for selecting voice, enabling features)
- Per-user vs per-machine install distinction
- Linux/macOS bundles — Windows-only is the project's permanent scope
- Bundling voice/wake models inside the .exe (they download on first run; spec leaves it that way for size)
- UPX compression (often breaks DLL loading; disabled in spec)
- `console=False` (windowless mode) — defer until logs are reliably going to file only

## 3. Decisions

| Question | Decision |
|---|---|
| Packaging tool | PyInstaller 6.x (single-folder mode, NOT `--onefile`) |
| Wrapper installer | None — portable zip distribution |
| Console window | `console=True` for now (users see startup errors); flip to False later |
| User-editable configs | Copied alongside `.exe` AFTER PyInstaller (not bundled into `_internal/`) |
| Read-only assets (icon) | Bundled via `--add-data` into `_MEIPASS` |
| Path resolution | New `paths.py` helper with `is_frozen()` / `get_resource_path()` / `get_user_config_dir()` |
| Build orchestration | Plain `build.bat` (no Make, no nox); developer-only — not in CI for now |
| ML models (whisper / piper / wake) | Stay download-on-first-run (already implemented); NOT bundled in installer |
| Default `tts/wake/llm` state after install | Off by default (matches `config/default.yaml` shipped state) |
| Uninstall | Just delete the folder; user data in `~/.voice-assistant/` survives unless user deletes |

## 4. Architecture

### 4.1 New files

```
installer/
├── voice_assistant.spec       # PyInstaller spec — explicit imports/datas
├── build.bat                   # Windows build script
├── runtime_hook.py             # UTF-8 stdio reconfiguration
└── README-USER.txt             # ships in the zip, 1-page guide

src/voice_assistant/utils/paths.py   # frozen-aware path resolution
tests/unit/utils/test_paths.py
```

### 4.2 Modified files

```
src/voice_assistant/main.py
  config_path = paths.get_user_config_path()   # not "config/default.yaml"

src/voice_assistant/ui/tray.py
  _DEFAULT_ICON_PATH = paths.get_resource_path("assets/tray-icon.png")

src/voice_assistant/nlu/rules.py  (or wherever commands.yaml is loaded in main)
  commands path derived from paths.get_user_config_dir() / "commands.yaml"

pyproject.toml
  + "pyinstaller>=6.0"  in dev extras

README.md
  + Build (developer) section
  + Install (end-user) section
```

`build.bat` adds `config/` and `README.txt` to the dist folder by `xcopy` after PyInstaller — no PyInstaller change needed for those.

### 4.3 Distribution layout

```
voice-assistant-0.1.0.zip
└── voice-assistant/
    ├── voice-assistant.exe         # entry point, ~5 MB launcher
    ├── _internal/                  # PyInstaller-generated, ~500 MB
    │   ├── python311.dll
    │   ├── faster_whisper/, piper/, openwakeword/, ...
    │   ├── assets/tray-icon.png    # bundled read-only asset
    │   └── (deps libs)
    ├── config/
    │   ├── default.yaml            # user-editable copy
    │   └── commands.yaml           # user-editable copy
    └── README.txt                  # 1-page user guide
```

User-experience contract:
- `_internal/` is implementation detail; user shouldn't touch it.
- `config/` is the place to tweak features.
- Logs and `voice_assistant.log` get written to the .exe's parent dir (where the user has write access).

### 4.4 `paths.py` interface

```python
# src/voice_assistant/utils/paths.py
import sys
from pathlib import Path


def is_frozen() -> bool:
    """True if running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def get_resource_path(relative: str) -> Path:
    """Resolve a read-only resource path bundled with the application.

    - In dev (running from source): repo_root / relative
    - When frozen: sys._MEIPASS / relative
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS")) / relative
    return Path(__file__).resolve().parents[3] / relative


def get_user_config_dir() -> Path:
    """Directory containing user-editable config (default.yaml + commands.yaml).

    - In dev: repo_root / "config"
    - When frozen: <exe-parent> / "config" (alongside the .exe, NOT in _internal/)
    """
    if is_frozen():
        return Path(sys.executable).parent / "config"
    return Path(__file__).resolve().parents[3] / "config"


def get_user_config_path() -> Path:
    """Full path to default.yaml."""
    return get_user_config_dir() / "default.yaml"
```

The `parents[3]` walk: `paths.py → utils → voice_assistant → src → <repo>`. This is the same trick the tray-icon fix used; consolidating it in one helper.

### 4.5 PyInstaller spec

```python
# installer/voice_assistant.spec
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).parent

hiddenimports = [
    "sounddevice",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "pynput._util.win32",
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "piper",
    "piper.config",
    "onnxruntime",
    "openwakeword",
    "openwakeword.model",
    "openwakeword.utils",
    "pycaw.pycaw",
    "comtypes.gen",
    "plyer.platforms.win.notification",
    "pystray._win32",
    "ollama",
    "pydantic",
    "pydantic_core",
    "yaml",
    "loguru",
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

### 4.6 Build script

```batch
@echo off
setlocal
set REPO_ROOT=%~dp0..
cd /d %REPO_ROOT%

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

.venv\Scripts\python.exe -m PyInstaller installer\voice_assistant.spec --noconfirm
if errorlevel 1 (
    echo PyInstaller failed.
    exit /b 1
)

xcopy /e /i /y config dist\voice-assistant\config\
copy /y installer\README-USER.txt dist\voice-assistant\README.txt

.venv\Scripts\python.exe -c "import shutil; shutil.make_archive('dist/voice-assistant-0.1.0', 'zip', 'dist', 'voice-assistant')"
if errorlevel 1 (
    echo Zip step failed.
    exit /b 1
)

echo.
echo Build complete: dist\voice-assistant-0.1.0.zip
```

### 4.7 Runtime hook

```python
# installer/runtime_hook.py
import sys
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
```

### 4.8 End-user README (ships in zip)

```
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

  Команды редактируются в config/commands.yaml.

UNINSTALL
  Просто удали эту папку. User data в %USERPROFILE%\.voice-assistant\
  (voice models, wake models) останется — удаляй вручную если нужно.

LOGS
  voice_assistant.log создаётся рядом с .exe.

ISSUES
  https://github.com/Laziz6066/assistant/issues
```

## 5. Error Handling

| Layer | Error | Behaviour |
|---|---|---|
| `paths.get_resource_path` | `sys._MEIPASS` missing while frozen | `AttributeError` propagates — install was corrupt; the user sees a clear traceback in console |
| `paths.get_user_config_path` | `config/default.yaml` missing alongside .exe | `load_config` raises FileNotFoundError → app exits with logged error — user is told to re-extract the zip |
| `build.bat` | PyInstaller fails (missing hidden import) | Exit code 1, error logged; developer adds the import to `voice_assistant.spec` |
| `build.bat` | Disk full while writing dist | xcopy errors, build.bat exits 1 |
| Runtime: pynput backend missing on frozen build | Already-handled by lazy import in `_make_keyboard_controller` → ImportError caught downstream |

## 6. Testing Strategy

### 6.1 What we test automatically

`tests/unit/utils/test_paths.py` (~6 tests):
- `is_frozen()` returns False when `sys.frozen` unset
- `is_frozen()` returns True when `sys.frozen=True` (monkeypatched)
- `get_resource_path("assets/x")` in dev → repo_root/assets/x
- `get_resource_path("assets/x")` when frozen → `_MEIPASS`/assets/x
- `get_user_config_dir()` in dev → repo_root/config
- `get_user_config_dir()` when frozen → `sys.executable`.parent / config

Plus extend `tests/unit/test_main.py` (~1):
- `_build` uses `paths.get_user_config_path()` (verify by monkeypatching paths module)

Plus extend `tests/unit/ui/test_tray.py` (~1):
- The existing path test still passes (paths helper preserves the same path in dev mode).

Plus a one-line smoke test for the spec syntactically loading:
- `python -c "from runpy import run_path; run_path('installer/voice_assistant.spec', init_globals={'SPECPATH': 'installer', 'Analysis': lambda *a, **kw: None, 'PYZ': lambda *a, **kw: None, 'EXE': lambda *a, **kw: None, 'COLLECT': lambda *a, **kw: None, 'block_cipher': None})"`
  (Hacky but catches typos. Optional.)

### 6.2 What stays manual

Per spec §6 of `2026-05-20-dictation-mode-design.md` convention, the hardware-touching parts are manually verified. For installer it's most of the surface:

- Actual PyInstaller build run (~3-5 min)
- Whether the produced .exe even starts
- Whether the tray icon renders
- Whether mic/keyboard/audio actually works
- Whether the .zip extracts cleanly on a different machine

### 6.3 What we don't test

- The packaged .exe's runtime behavior in CI (no Windows CI for this project right now)
- Antivirus false-positives (Defender sometimes flags PyInstaller-bundled .exe — unrelated to our code, varies per AV vendor and exe signature state)
- Code signing
- Different Windows versions (developer tests on the machine they have)

## 7. Manual Verification Checklist

Append to `README.md`:

- [ ] `installer\build.bat` завершается без ошибок (~3-5 минут)
- [ ] `dist/voice-assistant-0.1.0.zip` создан, ~500 MB
- [ ] Распаковка в чистую папку (без виртуального окружения рядом)
- [ ] Двойной клик по `voice-assistant.exe` — окно консоли + иконка в трее
- [ ] PTT: Right Ctrl → "открой блокнот" → notepad запускается
- [ ] `voice_assistant.log` создаётся рядом с .exe
- [ ] Включить `tts.enabled: true` в `config/default.yaml` → перезапустить → голос качается в `%USERPROFILE%\.voice-assistant\voices\`
- [ ] Tray → Quit → процесс корректно завершается, лог-файл не залочен
- [ ] Удалить папку → нет следов в Program Files / реестре
- [ ] (Опционально) Защитник Windows не флагует .exe как malware

## 8. Build & Install Documentation (README additions)

```markdown
## Build (для разработчика)

Производит portable .zip с .exe и user-editable configs:

```
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
installer\build.bat
```

Результат: `dist/voice-assistant-0.1.0.zip` (~500 MB).

Сборка занимает 3-5 минут. Если падает на missing hidden import — добавь его в `hiddenimports` в `installer/voice_assistant.spec`.

## Install (для конечного пользователя)

1. Скачай `voice-assistant-0.1.0.zip` с релизной страницы
2. Распакуй в удобную папку (например, `C:\Apps\voice-assistant\`)
3. Запусти `voice-assistant.exe`
4. Опционально отредактируй `config/default.yaml` чтобы включить TTS / wake / LLM / dictation

User data (voice models, wake models) хранится в `%USERPROFILE%\.voice-assistant\`. Удаление папки приложения её не очищает — удали вручную если нужен полный clean.
```

## 9. Open Questions / Future Work

- **Inno Setup wizard** — даёт Start Menu shortcut, opt-in autostart, uninstaller в Programs and Features. Логичное следующее улучшение поверх portable.
- **Code signing** — без подписи Windows SmartScreen покажет warning на первом запуске. Подпись = $200-500/год за cert. Defer.
- **Bundled voice model** — текущий 500MB dist уже большой; +63MB голоса = 600MB. Альтернатива: качаем на первом запуске (текущее поведение). OK.
- **`console=False`** — переключить когда все ошибки уверенно идут только в `voice_assistant.log`, не в stdout/stderr.
- **CI build** — GitHub Actions Windows runner может производить .zip по push'у тега. ~30 минут per build. Отложено.
- **`.exe` icon** — `tray-icon.png` отрисуется PyInstaller'ом как .ico автоматически, но качество ноль. В будущем — сделать proper .ico с разрешениями 16/32/64/256.

## 10. References

- PyInstaller spec: https://pyinstaller.org/en/stable/spec-files.html
- PyInstaller hidden imports: https://pyinstaller.org/en/stable/when-things-go-wrong.html#listing-hidden-imports
- `sys._MEIPASS`: https://pyinstaller.org/en/stable/runtime-information.html
- MVP design: `docs/superpowers/specs/2026-05-19-voice-assistant-design.md`
- Tray spec (which fixed icon paths first): `docs/superpowers/specs/2026-05-20-system-tray-design.md`
