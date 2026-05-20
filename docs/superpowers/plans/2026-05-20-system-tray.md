# System Tray Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent system-tray icon with a right-click menu (About / Quit) so the user can see the assistant is running and shut it down cleanly without finding the console window.

**Architecture:** New `SystemTray` class owns a `pystray.Icon`, runs it on a daemon thread. Quit menu item calls a shutdown callback that funnels through the same `_request_shutdown` helper SIGINT uses. Any pystray failure (import error, no graphical session) degrades cleanly to `tray=None`, ассистент работает без иконки.

**Tech Stack:** Python 3.11+, pystray ≥0.19, Pillow ≥10 (already a transitive dep), threading.

**Depends on:** voice-assistant branch at commit `c354635` or later. Spec: `docs/superpowers/specs/2026-05-20-system-tray-design.md`.

---

## File Structure

**New files:**
- `src/voice_assistant/ui/__init__.py` — empty package marker
- `src/voice_assistant/ui/tray.py` — `SystemTray` class
- `assets/tray-icon.png` — 64x64 PNG icon shipped with the repo
- `tests/unit/ui/__init__.py` — needed for pytest module disambiguation (we already have one in `tests/unit/activation/` and `tests/unit/feedback/`)
- `tests/unit/ui/test_tray.py` — unit tests

**Modified files:**
- `src/voice_assistant/config.py` — add `TrayConfig` + `AppConfig.tray`
- `src/voice_assistant/main.py` — extract `_request_shutdown` to module-level; build `SystemTray` when `cfg.tray.enabled`; integrate `tray.start()` / `tray.stop()`; bind tray's quit_callback in `main()` after `stop_evt` is created
- `config/default.yaml` — add `tray` section
- `pyproject.toml` — add `pystray>=0.19`
- `README.md` — append System Tray section + manual checklist
- `tests/unit/test_config.py` — extend with `TrayConfig` tests
- `tests/unit/test_main.py` — extend with `_build` tray-wiring tests

---

## Task 1: `TrayConfig` in `config.py`

**Files:**
- Modify: `src/voice_assistant/config.py`
- Test: extend `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py`:

```python
from voice_assistant.config import TrayConfig


def test_tray_config_default_enabled():
    cfg = TrayConfig()
    assert cfg.enabled is True


def test_tray_config_accepts_disabled():
    cfg = TrayConfig(enabled=False)
    assert cfg.enabled is False


def test_app_config_has_tray_section_default_enabled():
    cfg = AppConfig()
    assert cfg.tray.enabled is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v -k tray`
Expected: 3 FAILs with `ImportError: cannot import name 'TrayConfig'`.

- [ ] **Step 3: Add `TrayConfig` and wire into `AppConfig`**

Edit `src/voice_assistant/config.py`. After the existing `WakeConfig` class and before `AppConfig`, insert:

```python
class TrayConfig(BaseModel):
    enabled: bool = True
```

Inside `AppConfig`, add the `tray` field (place it after `wake`):

```python
tray: TrayConfig = Field(default_factory=TrayConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v -k tray`
Expected: 3 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 3 = 189.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/config.py tests/unit/test_config.py
git commit -m "feat(config): add TrayConfig with enabled=true default"
```

---

## Task 2: Dependencies + `config/default.yaml` + asset

This task installs `pystray`, adds the yaml section, and ships a placeholder icon PNG. Comes BEFORE Task 3 so module-level `import pystray` resolves in tests.

**Files:**
- Modify: `pyproject.toml`
- Modify: `config/default.yaml`
- Create: `assets/tray-icon.png`

- [ ] **Step 1: Add `pystray` to `pyproject.toml`**

In the `[project] dependencies = [...]` list, append:

```toml
  "pystray>=0.19",
```

- [ ] **Step 2: Add `tray` section to `config/default.yaml`**

Append:

```yaml
tray:
  enabled: true
```

- [ ] **Step 3: Generate placeholder icon PNG**

The icon ships in the repo at `assets/tray-icon.png` — 64x64 RGBA. Generate it programmatically from the worktree root:

```bash
.\.venv\Scripts\python.exe -c "from PIL import Image, ImageDraw; img = Image.new('RGBA', (64, 64), (0,0,0,0)); d = ImageDraw.Draw(img); d.ellipse((4,4,60,60), fill=(30,120,220,255)); d.text((18,22), 'VA', fill='white'); import os; os.makedirs('assets', exist_ok=True); img.save('assets/tray-icon.png')"
```

Verify the file exists:

```bash
.\.venv\Scripts\python.exe -c "from PIL import Image; im = Image.open('assets/tray-icon.png'); print(im.size, im.mode)"
```
Expected: `(64, 64) RGBA`

- [ ] **Step 4: Install + smoke check**

```bash
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -c "import pystray; from pystray import Icon, MenuItem, Menu; print('OK')"
.\.venv\Scripts\python.exe -c "from voice_assistant.config import load_config; c = load_config('config/default.yaml'); print(c.tray)"
```
Expected:
- `OK` printed
- `enabled=True` for tray section

If `pystray` fails to install (Linux without X libs, etc.), STOP and report BLOCKED — do NOT silently substitute a different library.

- [ ] **Step 5: Full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green (no new tests this task).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml config/default.yaml assets/tray-icon.png
git commit -m "chore(deps): add pystray>=0.19 + tray section + placeholder icon"
```

---

## Task 3: `SystemTray` class

**Files:**
- Create: `src/voice_assistant/ui/__init__.py` (empty)
- Create: `src/voice_assistant/ui/tray.py`
- Create: `tests/unit/ui/__init__.py` (empty — disambiguates `test_tray.py` from any sibling)
- Create: `tests/unit/ui/test_tray.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/ui/test_tray.py
import time
import threading
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from voice_assistant.ui.tray import SystemTray


def _make_quit_cb():
    return MagicMock()


def test_init_constructs_icon_with_menu():
    quit_cb = _make_quit_cb()
    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu") as MockMenu, \
         patch("voice_assistant.ui.tray.pystray.MenuItem") as MockMenuItem, \
         patch("voice_assistant.ui.tray._load_icon") as MockLoadIcon:
        MockLoadIcon.return_value = MagicMock(name="image")
        tray = SystemTray(quit_callback=quit_cb, version="0.2.0")
    # Icon was constructed
    MockIcon.assert_called_once()
    # Two menu items: About and Quit
    assert MockMenuItem.call_count == 2
    menu_texts = [call.args[0] for call in MockMenuItem.call_args_list]
    assert "About" in menu_texts
    assert "Quit" in menu_texts


def test_start_spawns_daemon_thread_and_runs_icon():
    quit_cb = _make_quit_cb()
    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem"), \
         patch("voice_assistant.ui.tray._load_icon"):
        # Icon.run blocks until Icon.stop is called; simulate with an Event
        run_event = threading.Event()
        inst = MagicMock()
        inst.run = MagicMock(side_effect=lambda: run_event.wait(timeout=2))
        inst.stop = MagicMock(side_effect=lambda: run_event.set())
        MockIcon.return_value = inst

        tray = SystemTray(quit_callback=quit_cb)
        tray.start()
        time.sleep(0.05)
        assert tray._thread is not None
        assert tray._thread.is_alive()
        assert tray._thread.daemon is True
        inst.run.assert_called()  # called from the spawned thread

        tray.stop()
        time.sleep(0.05)
        assert not tray._thread.is_alive()


def test_stop_calls_icon_stop_and_joins():
    quit_cb = _make_quit_cb()
    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem"), \
         patch("voice_assistant.ui.tray._load_icon"):
        run_event = threading.Event()
        inst = MagicMock()
        inst.run = MagicMock(side_effect=lambda: run_event.wait(timeout=2))
        inst.stop = MagicMock(side_effect=lambda: run_event.set())
        MockIcon.return_value = inst

        tray = SystemTray(quit_callback=quit_cb)
        tray.start()
        time.sleep(0.05)
        tray.stop()
        inst.stop.assert_called_once()


def test_stop_is_idempotent():
    quit_cb = _make_quit_cb()
    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem"), \
         patch("voice_assistant.ui.tray._load_icon"):
        inst = MagicMock()
        MockIcon.return_value = inst
        tray = SystemTray(quit_callback=quit_cb)
        # stop() before start() must not raise
        tray.stop()
        tray.stop()  # second call also no-op


def test_quit_menu_invokes_callback_and_stops_icon():
    quit_cb = _make_quit_cb()
    captured = {}

    def capture_menu_items(*args, **kwargs):
        # Mimic pystray.MenuItem signature: (text, action, ...)
        text = args[0]
        action = args[1] if len(args) > 1 else None
        captured[text] = action
        return MagicMock(name=f"item_{text}")

    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem",
                side_effect=capture_menu_items), \
         patch("voice_assistant.ui.tray._load_icon"):
        inst = MagicMock()
        MockIcon.return_value = inst
        tray = SystemTray(quit_callback=quit_cb)
        # Now invoke the Quit action like pystray would
        quit_action = captured["Quit"]
        assert quit_action is not None
        quit_action(inst, MagicMock())  # pystray calls action(icon, item)
        quit_cb.assert_called_once()
        inst.stop.assert_called_once()


def test_about_menu_does_not_invoke_quit_callback():
    quit_cb = _make_quit_cb()
    captured = {}

    def capture_menu_items(*args, **kwargs):
        text = args[0]
        action = args[1] if len(args) > 1 else None
        captured[text] = action
        return MagicMock(name=f"item_{text}")

    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem",
                side_effect=capture_menu_items), \
         patch("voice_assistant.ui.tray._load_icon"):
        inst = MagicMock()
        MockIcon.return_value = inst
        tray = SystemTray(quit_callback=quit_cb, version="9.9.9")
        about_action = captured["About"]
        # Invoke About — should not call quit_cb
        about_action(inst, MagicMock())
        quit_cb.assert_not_called()


def test_load_icon_uses_path_when_exists(tmp_path):
    """If icon_path is a real file, _load_icon delegates to Image.open."""
    from voice_assistant.ui.tray import _load_icon
    # Create a tiny valid PNG file
    from PIL import Image
    p = tmp_path / "icon.png"
    Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(p)
    img = _load_icon(p)
    assert img.size == (16, 16)


def test_load_icon_fallback_when_path_missing(tmp_path):
    """If icon_path is None or doesn't exist, returns a programmatic icon."""
    from voice_assistant.ui.tray import _load_icon
    img = _load_icon(None)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"
    # Try with non-existent path
    img2 = _load_icon(tmp_path / "missing.png")
    assert img2.size == (64, 64)


def test_quit_callback_raising_still_calls_icon_stop():
    """If quit_callback throws, the menu handler must still call icon.stop."""
    quit_cb = MagicMock(side_effect=RuntimeError("boom"))
    captured = {}

    def capture_menu_items(*args, **kwargs):
        text = args[0]
        action = args[1] if len(args) > 1 else None
        captured[text] = action
        return MagicMock()

    with patch("voice_assistant.ui.tray.pystray.Icon") as MockIcon, \
         patch("voice_assistant.ui.tray.pystray.Menu"), \
         patch("voice_assistant.ui.tray.pystray.MenuItem",
                side_effect=capture_menu_items), \
         patch("voice_assistant.ui.tray._load_icon"):
        inst = MagicMock()
        MockIcon.return_value = inst
        tray = SystemTray(quit_callback=quit_cb)
        quit_action = captured["Quit"]
        quit_action(inst, MagicMock())  # raises inside quit_cb
        inst.stop.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/ui/test_tray.py -v`
Expected: 9 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `SystemTray`**

Create `src/voice_assistant/ui/__init__.py`:

```python
```

(empty file)

Create `tests/unit/ui/__init__.py`:

```python
```

(empty file — disambiguates test module name)

Create `src/voice_assistant/ui/tray.py`:

```python
from __future__ import annotations
import threading
from collections.abc import Callable
from pathlib import Path
from loguru import logger

import pystray
from PIL import Image, ImageDraw


_DEFAULT_ICON_PATH = Path("assets/tray-icon.png")
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
            self._thread = None

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/ui/test_tray.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 9 = 198.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/ui/__init__.py src/voice_assistant/ui/tray.py tests/unit/ui/__init__.py tests/unit/ui/test_tray.py
git commit -m "feat(ui): SystemTray with About/Quit menu and graceful failure"
```

---

## Task 4: Refactor `_shutdown` to module-level helper

Extract the closure-based `_shutdown` in `main()` into a module-level `_request_shutdown` so the tray's quit menu can call the same path without reaching into `main()`'s local scope.

**Files:**
- Modify: `src/voice_assistant/main.py`
- Test: extend `tests/unit/test_main.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_main.py`:

```python
def test_request_shutdown_sets_event_and_puts_stop_and_cancels_feedback():
    import threading as _t
    from voice_assistant.main import _request_shutdown
    from voice_assistant.core.queues import STOP

    stop_evt = _t.Event()
    qs = MagicMock()
    qs.speech_q = MagicMock()
    feedback = MagicMock()

    _request_shutdown(stop_evt, qs, feedback)

    assert stop_evt.is_set()
    qs.speech_q.put_nowait.assert_called_once_with(STOP)
    feedback.cancel.assert_called_once()


def test_request_shutdown_swallows_queue_full():
    import queue as _q
    import threading as _t
    from voice_assistant.main import _request_shutdown

    stop_evt = _t.Event()
    qs = MagicMock()
    qs.speech_q = MagicMock()
    qs.speech_q.put_nowait.side_effect = _q.Full()
    feedback = MagicMock()

    # Must NOT raise even when queue is full
    _request_shutdown(stop_evt, qs, feedback)
    assert stop_evt.is_set()
    feedback.cancel.assert_called_once()


def test_request_shutdown_swallows_feedback_cancel_failure():
    import threading as _t
    from voice_assistant.main import _request_shutdown

    stop_evt = _t.Event()
    qs = MagicMock()
    qs.speech_q = MagicMock()
    feedback = MagicMock()
    feedback.cancel.side_effect = RuntimeError("boom")

    # Must NOT propagate the exception
    _request_shutdown(stop_evt, qs, feedback)
    assert stop_evt.is_set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k request_shutdown`
Expected: 3 FAILs with `ImportError: cannot import name '_request_shutdown'`.

- [ ] **Step 3: Edit `main.py`**

a) Near the top of `main.py`, after the imports, add the module-level helper:

```python
def _request_shutdown(stop_evt: threading.Event,
                       qs: PipelineQueues,
                       feedback: FeedbackSink) -> None:
    """Idempotent shutdown trigger used by SIGINT and the tray Quit menu.

    Sets the worker's stop event, puts the STOP sentinel onto the speech
    queue (swallowing queue.Full), and cancels any in-flight feedback.
    Safe to call multiple times.
    """
    logger.info("shutting down")
    stop_evt.set()
    try:
        qs.speech_q.put_nowait(STOP)
    except queue.Full:
        pass
    try:
        feedback.cancel()
    except Exception:
        logger.exception("feedback.cancel during shutdown failed")
```

b) In the body of `main()`, find the current `_shutdown` closure:

```python
    def _shutdown(*_):
        logger.info("shutting down")
        stop_evt.set()
        qs.speech_q.put(STOP)
        try:
            feedback.cancel()
        except Exception:
            pass
```

Replace it with:

```python
    def _shutdown(*_):
        _request_shutdown(stop_evt, qs, feedback)
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k request_shutdown`
Expected: 3 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 3 = 201. **No regressions** — the previous SIGINT-shutdown flow is unchanged behaviorally.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/main.py tests/unit/test_main.py
git commit -m "refactor(main): extract _request_shutdown to module-level helper"
```

---

## Task 5: Wire `SystemTray` into `_build` and `main()`

**Files:**
- Modify: `src/voice_assistant/main.py`
- Test: extend `tests/unit/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_main.py`:

```python
def test_build_returns_tray_when_enabled(tmp_path, monkeypatch):
    """When tray.enabled, _build returns a 7-tuple ending with a SystemTray."""
    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    fake_tray = MagicMock(name="SystemTray-instance")
    monkeypatch.setattr("voice_assistant.main.SystemTray",
                        MagicMock(return_value=fake_tray))

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n"
        "tray:\n  enabled: true\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback, tray = _build(
        str(tmp_path / "default.yaml"))
    assert tray is fake_tray


def test_build_returns_none_tray_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n"
        "tray:\n  enabled: false\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback, tray = _build(
        str(tmp_path / "default.yaml"))
    assert tray is None


def test_build_returns_none_tray_when_systemtray_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    bad = MagicMock(side_effect=RuntimeError("pystray not available"))
    monkeypatch.setattr("voice_assistant.main.SystemTray", bad)

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n"
        "tray:\n  enabled: true\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback, tray = _build(
        str(tmp_path / "default.yaml"))
    assert tray is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "tray_when_enabled or tray_when_disabled or tray_when_systemtray_raises"`
Expected: FAILs — `_build` still returns 6-tuple OR `SystemTray` not yet imported into main.

- [ ] **Step 3: Edit `main.py`**

a) Add the SystemTray import near the other UI/activator imports:

```python
from voice_assistant.ui.tray import SystemTray
```

b) Find the current `_build` return statement at the end of the function:

```python
    if len(activators) > 1:
        ptt = CompositeActivator(activators)
    return pipe, qs, capture, ptt, vad, feedback
```

Replace with:

```python
    if len(activators) > 1:
        ptt = CompositeActivator(activators)

    tray: SystemTray | None = None
    if cfg.tray.enabled:
        try:
            tray = SystemTray(quit_callback=lambda: None, version="0.1.0")
        except Exception as e:
            logger.error(f"tray disabled — setup failed: {e}")
            tray = None

    return pipe, qs, capture, ptt, vad, feedback, tray
```

The `quit_callback=lambda: None` is a placeholder — `main()` rebinds it once `stop_evt` exists (next step).

c) Update the signature/return-type annotation of `_build`. Find:

```python
def _build(config_path: str) -> tuple[Pipeline, PipelineQueues,
                                       AudioCapture, PushToTalk, VADSegmenter,
                                       FeedbackSink]:
```

Replace with:

```python
def _build(config_path: str) -> tuple[Pipeline, PipelineQueues,
                                       AudioCapture, Activator, VADSegmenter,
                                       FeedbackSink, SystemTray | None]:
```

(If the implementer of Task 8 of wake-word already changed `PushToTalk → Activator`, this matches; just add the trailing `SystemTray | None`.)

d) In `main()`, find the unpack:

```python
    pipe, qs, capture, ptt, vad, feedback = _build(config_path)
```

Replace with:

```python
    pipe, qs, capture, ptt, vad, feedback, tray = _build(config_path)
```

e) After `signal.signal(signal.SIGINT, _shutdown)` is set, but BEFORE `ptt.start()`, bind the real quit callback and start the tray:

```python
    signal.signal(signal.SIGINT, _shutdown)
    if tray is not None:
        tray._quit_callback = lambda: _shutdown()
        try:
            tray.start()
        except Exception:
            logger.exception("tray.start failed")
            tray = None
    ptt.start()
```

The direct attribute write `tray._quit_callback = ...` is acceptable because `SystemTray` exposes `_quit_callback` and the closure captured at construction was a no-op placeholder. We document this in the SystemTray docstring of Task 3 as "the placeholder is meant to be rebound before start()" — actually that's not documented. So instead use a public setter approach: add a `set_quit_callback` method to `SystemTray`:

(Alternative b — cleaner; do this instead of direct attribute write.)

Edit `src/voice_assistant/ui/tray.py` to add the setter on the `SystemTray` class:

```python
    def set_quit_callback(self, callback: Callable[[], None]) -> None:
        """Replace the quit callback. Useful when the real callback isn't
        available at construction time (e.g. it captures objects created
        later in main())."""
        self._quit_callback = callback
```

And update the main.py block to:

```python
    signal.signal(signal.SIGINT, _shutdown)
    if tray is not None:
        tray.set_quit_callback(lambda: _shutdown())
        try:
            tray.start()
        except Exception:
            logger.exception("tray.start failed")
            tray = None
    ptt.start()
```

f) In `main()`'s shutdown section, find:

```python
    worker.join()
    feedback.stop()
    ptt.stop()
    capture.stop()
    return 0
```

Replace with:

```python
    worker.join()
    if tray is not None:
        try:
            tray.stop()
        except Exception:
            logger.exception("tray.stop failed")
    feedback.stop()
    ptt.stop()
    capture.stop()
    return 0
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "tray_when_enabled or tray_when_disabled or tray_when_systemtray_raises"`
Expected: 3 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 3 = 204. **Watch for regressions** — every test that unpacks `_build` (the wake-word task added some) MUST now unpack 7 elements. Update any that still unpack 6.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/main.py src/voice_assistant/ui/tray.py tests/unit/test_main.py
git commit -m "feat(main): wire SystemTray into _build and main lifecycle"
```

---

## Task 6: README + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append System tray section + manual checklist**

Below the existing "Wake-word verification checklist" section, append:

```markdown

## System tray

Когда ассистент запущен, в системном трее появляется иконка. Правой кнопкой:
- **About** — версия ассистента (вывод в лог)
- **Quit** — корректное завершение работы (как Ctrl+C)

Отключить трей: `tray.enabled: false` в `config/default.yaml` — ассистент работает без иконки (полезно для headless/автозапуска без UI).

Если `pystray` не установлен или нет графической сессии (Linux без X/Wayland) — трей тихо отключается, ассистент работает.

## System-tray verification checklist

- [ ] Запустить — иконка появляется в трее
- [ ] Hover показывает tooltip "Voice Assistant"
- [ ] Right-click → About → версия в логе
- [ ] Right-click → Quit → ассистент корректно завершается, без traceback
- [ ] Ctrl+C тоже завершает корректно (тот же путь через `_request_shutdown`)
- [ ] `tray.enabled: false` → иконки нет, ассистент работает в консоли
- [ ] Удалить assets/tray-icon.png → запустить → fallback иконка (синий круг "VA") показывается
```

- [ ] **Step 2: Run full test suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green at 204.

- [ ] **Step 3: Coverage check**

Run: `.\.venv\Scripts\python.exe -m pytest --cov=voice_assistant --cov-report=term-missing -q`
Expected: new modules at ≥ 80%:
- `ui/tray.py` — should approach 90% (some exception-handler branches may be hard to hit cleanly)
- `config.py` — still ≥ 92%

Note any module below 80% in your commit message.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: system tray setup notes + manual checklist"
```

---

## Self-Review Notes

- **Spec coverage:**
  - TrayConfig (T1)
  - pystray dep + yaml + icon asset (T2)
  - SystemTray class with About/Quit + failure modes (T3)
  - `_request_shutdown` module-level helper for shared shutdown path (T4)
  - `_build` wires tray + `main()` lifecycle (T5)
  - README + checklist (T6)

  All failure modes from spec §6 covered: pystray import fail (T5 test_build_returns_none_tray_when_systemtray_raises), Icon.run raise (T3 test_quit_callback_raising_still_calls_icon_stop via _run_safely), idempotent stop (T3 test_stop_is_idempotent), graceful absence (T3 test_load_icon_fallback_when_path_missing), quit_callback re-bind (T5 step 3.e).

- **Task ordering:**
  - T2 (install pystray) MUST come before T3 (module-level `import pystray`)
  - T4 (extract `_request_shutdown`) MUST come before T5 (wires its lambda into tray)
  - T1 (TrayConfig) is independent of T2-T6 but logically first

- **Type consistency:**
  - `SystemTray(quit_callback, version, icon_path)` signature used in T3 matches the call in T5
  - `_request_shutdown(stop_evt, qs, feedback)` signature in T4 matches the call sites in T5's `_shutdown` lambda
  - `_build` returns a 7-tuple after T5 — every existing test that unpacks `_build` was already updated to 6-tuple by wake-word Task 8; T5 step 5 explicitly flags the need to update them again to 7-tuple

- **Out of scope (per spec §10):** state indicator icon, feature toggles in menu, show-logs item, custom icon themes, balloon notifications. If tempted, STOP.

- **Test density:** ~18 new tests across 4 test files. Expected total after T6: ~204 (current 186 + 18).
