# System Tray — Design Spec

**Date:** 2026-05-20
**Status:** Approved, ready for implementation plan
**Sub-project:** Beta (post-MVP, post-Piper-TTS, post-ollama-fallback, post-wake-word)
**Depends on:** voice-assistant branch at commit `b876874` or later

## 1. Goal

Add a persistent system-tray icon so the user has visual confirmation the assistant is running, and a clean "Quit" menu item to shut it down without hunting for the console window.

## 2. Scope

**In:**
- Static tray icon while the assistant is running (16x16 / 64x64 PNG)
- Right-click context menu: **About** (version popup), **Quit** (graceful shutdown)
- New `SystemTray` class that owns a `pystray.Icon` and runs it on a daemon thread
- `TrayConfig.enabled` in `config.py` (default `true`)
- Graceful degrade: any pystray failure (import, init, run) → log error, ассистент работает без иконки

**Out (deferred):**
- Dynamic icon reflecting IDLE / LISTENING / PROCESSING state
- Toggle menu items for wake/TTS/LLM (would require hot-config-reload across all subsystems)
- Tray balloon notifications (plyer already provides desktop notifications)
- Linux distro-specific testing (Windows-first; pystray is cross-platform so it should work on Linux/macOS, but unverified)
- "Show logs" menu item

## 3. Decisions

| Question | Decision |
|---|---|
| Library | `pystray` (cross-platform, pure Python, mature) |
| Default `enabled` | `true` (no external resources required; clean desktop UX) |
| Icon | Static PNG shipped in `assets/tray-icon.png` |
| Quit semantics | Calls existing SIGINT-equivalent shutdown path (sets `stop_evt`, puts `STOP` on `speech_q`) |
| Failure policy | Any pystray exception → log + `tray=None` → ассистент работает без tray |
| Threading | `pystray.Icon.run()` blocks → spawn daemon thread; `stop()` calls `icon.stop()` to unblock |

## 4. Architecture

### 4.1 New files

```
src/voice_assistant/ui/
  __init__.py
  tray.py             # SystemTray(quit_callback, version)

assets/
  tray-icon.png       # 64x64 PNG icon shipped with repo

tests/unit/ui/
  __init__.py
  test_tray.py
```

### 4.2 Modified files

```
src/voice_assistant/config.py
  + class TrayConfig(BaseModel):
        enabled: bool = True
  + AppConfig.tray: TrayConfig

src/voice_assistant/main.py
  Build tray if cfg.tray.enabled; integrate start()/stop() into the
  existing lifecycle. Extract _shutdown into a module-level helper
  _request_shutdown(stop_evt, qs, feedback) so the tray's quit menu
  can call it without reaching into main()'s locals.

pyproject.toml
  + pystray>=0.19

README.md
  + Tray section + manual checklist additions
```

### 4.3 `SystemTray` interface

```python
class SystemTray:
    """Persistent system-tray icon with right-click menu.

    Lifecycle:
      __init__(quit_callback, version) — builds the pystray.Icon object;
        does NOT block, does NOT spawn threads.
      start() — spawns a daemon thread that runs Icon.run(); returns
        immediately.
      stop()  — calls Icon.stop() so the daemon thread exits; joins
        with 2s timeout.

    Menu:
      About → opens a native message box with the version string
        (Windows: ctypes.windll.user32.MessageBoxW; cross-platform
        fallback: logger.info + plyer notification).
      Quit  → invokes quit_callback() then Icon.stop().

    Failure policy: SystemTray construction may raise on import or
    icon-build errors. main._build() catches these and proceeds with
    tray=None.
    """

    def __init__(self, quit_callback: Callable[[], None],
                 version: str = "0.1.0",
                 icon_path: Path | None = None): ...

    def start(self) -> None: ...
    def stop(self) -> None: ...
```

### 4.4 Icon loading

```python
def _load_icon(icon_path: Path | None) -> Image.Image:
    if icon_path is not None and icon_path.is_file():
        return Image.open(icon_path)
    # Fallback: programmatic 64x64 transparent-bg icon with "VA" text
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(30, 120, 220, 255))
    draw.text((18, 18), "VA", fill="white")
    return img
```

Test mode bypasses real `Image.open` via mock.

### 4.5 Shutdown integration

The existing `_shutdown` handler in `main()` is currently a nested closure that captures `stop_evt`, `qs`, and `feedback`. To let the tray's Quit menu reuse it cleanly, refactor it into a module-level function:

```python
def _request_shutdown(stop_evt: threading.Event,
                       qs: PipelineQueues,
                       feedback: FeedbackSink) -> None:
    logger.info("shutting down")
    stop_evt.set()
    try:
        qs.speech_q.put_nowait(STOP)
    except queue.Full:
        pass
    try:
        feedback.cancel()
    except Exception:
        pass
```

And `main()` builds a `quit_callback = lambda: _request_shutdown(stop_evt, qs, feedback)` to pass into `SystemTray.__init__`. SIGINT handler becomes `lambda *_: _request_shutdown(stop_evt, qs, feedback)`. Both paths funnel through the same function — idempotent on repeated calls (set/discard semantics on the event).

### 4.6 Lifecycle order in `main()`

```python
def main() -> int:
    pipe, qs, capture, ptt, vad, feedback, tray = _build(config_path)
    stop_evt = threading.Event()
    try:
        capture.start()
    except Exception as e:
        logger.error(f"microphone unavailable: {e}")
        return 1
    feedback.start()

    def _shutdown(*_):
        _request_shutdown(stop_evt, qs, feedback)

    signal.signal(signal.SIGINT, _shutdown)
    if tray is not None:
        tray.quit_callback = _shutdown  # bind late; OR pass at construction
        tray.start()
    ptt.start()
    worker = threading.Thread(...)
    worker.start()
    logger.info("ready — ...")
    worker.join()
    if tray is not None:
        tray.stop()
    feedback.stop()
    ptt.stop()
    capture.stop()
    return 0
```

The `quit_callback` is bound at SystemTray construction time, but since construction happens in `_build` before `stop_evt` exists, the cleanest approach is to construct `SystemTray` with a placeholder and replace `tray.quit_callback` in `main()` before `tray.start()`. Alternative: pass a `Callable[[], None]` that is `lambda: None` initially and `main()` calls `tray.set_quit_callback(real_callback)` before start. Implementation chooses one.

## 5. Configuration

```yaml
# config/default.yaml
tray:
  enabled: true
```

When `enabled: false`, `_build()` does not import `pystray` and returns `tray=None`. No CPU cost.

## 6. Error Handling

| Layer | Error | Behaviour |
|---|---|---|
| `SystemTray.__init__` | `pystray` not importable | Raise — `_build` catches, sets `tray=None` |
| `SystemTray.__init__` | Icon file missing | Use programmatic fallback (see §4.4) |
| `SystemTray.__init__` | Pillow not importable | Raise — `_build` catches |
| `SystemTray.start` | `Icon.run` raises on the daemon thread | `logger.exception`, daemon thread exits, main thread unaffected |
| `SystemTray.stop` | Already stopped | Idempotent (no-op) |
| Quit menu click | `quit_callback` raises | `logger.exception` then call `Icon.stop()` regardless |
| `quit_callback` invoked multiple times | Calling `_request_shutdown` again is safe — `stop_evt.set()` is idempotent, `put_nowait(STOP)` may raise `queue.Full` (caught), `feedback.cancel()` is idempotent |

## 7. Testing Strategy

### 7.1 Mocks

- `pystray.Icon` and `pystray.MenuItem`/`Menu` — patched at module-level in `voice_assistant.ui.tray`
- `PIL.Image.open` and `PIL.ImageDraw` — patched for icon-loading tests
- No real tray window is ever created in tests

### 7.2 Unit tests (target ≥80% on `tray.py`)

`tests/unit/ui/test_tray.py`:
- `SystemTray.__init__` constructs `pystray.Icon` with the expected name, image, and menu items
- Menu has exactly two items: "About" and "Quit"
- `start()` spawns a daemon thread that calls `Icon.run`
- `stop()` calls `Icon.stop` and joins the thread within timeout
- Quit menu item invokes `quit_callback` exactly once
- About menu item does NOT call `quit_callback`
- Multiple `stop()` calls are idempotent (no exception)
- Icon path argument: if file exists, `PIL.Image.open` is called; if not, fallback drawing is invoked

`tests/unit/test_main.py` (extend):
- `_build` returns a 7-tuple including `tray` when `tray.enabled=true`
- `_build` sets `tray=None` when `tray.enabled=false`
- `_build` sets `tray=None` when `SystemTray.__init__` raises

`tests/unit/test_config.py` (extend):
- `TrayConfig()` defaults: `enabled=True`
- `AppConfig().tray.enabled` is `True` by default

### 7.3 What we don't test

- Real pystray rendering (mocked)
- Actual tray click events in CI (mocked)
- Platform-specific behavior on Linux/macOS (Windows-first; pystray docs cover others)

## 8. README addition

```markdown
## System tray

Когда ассистент запущен, в системном трее появляется иконка. Правой кнопкой мыши:
- **About** — версия ассистента
- **Quit** — корректное завершение работы

Отключить трей: в `config/default.yaml` поставь `tray.enabled: false` — ассистент будет работать без иконки (полезно для headless-режимов / автозапуска без UI).

Если `pystray` не установлен или система без графической сессии (Linux без X/Wayland) — трей тихо отключается, ассистент работает.
```

## 9. Manual Verification Checklist (append to README)

- [ ] Запустить — иконка появляется в трее
- [ ] Hover показывает tooltip "Voice Assistant"
- [ ] Right-click → About → видна версия
- [ ] Right-click → Quit → ассистент корректно завершается (без traceback)
- [ ] Ctrl+C тоже завершает корректно
- [ ] `tray.enabled: false` → иконки нет, ассистент работает в консоли
- [ ] Удалить assets/tray-icon.png → запустить → fallback иконка показывается

## 10. Open Questions / Future Work

- **Indicator состояния** (IDLE/LISTENING/PROCESSING) — нужно гонять событие из активатора и pipeline в tray-нить. ~80 строк, отдельная итерация.
- **Toggle wake/TTS/LLM из трея** — требует hot-reload в каждом компоненте. Большой redesign, post-MVP.
- **"Show logs" menu** — открыть текущий лог в Notepad/default editor. Тривиально (~5 строк), но требует знать путь к log file.
- **Tray notifications** — pystray поддерживает `.notify(message)`, можно вытащить из plyer на pystray. Мелочь.
- **Custom icon themes** — `tray.icon: <path>` в config для пользовательских иконок. Тривиально расширить `_load_icon`.

## 11. References

- pystray: https://pystray.readthedocs.io/
- Pillow Image API: https://pillow.readthedocs.io/en/stable/reference/Image.html
- Voice-assistant MVP spec: `docs/superpowers/specs/2026-05-19-voice-assistant-design.md`
- Piper TTS spec: `docs/superpowers/specs/2026-05-20-piper-tts-design.md`
- Wake-word spec: `docs/superpowers/specs/2026-05-20-wake-word-design.md`
