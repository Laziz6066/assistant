# Dictation Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a voice-toggled dictation mode that types transcripts as keystrokes into the active window, with a fixed punctuation-word map (`точка → .`, `новая строка → \n`, etc.). When in dictation mode the pipeline bypasses NLU dispatch (except for `stop_dictation`) and skips multi-turn context updates.

**Architecture:** A small `ModeStore` (state + Lock) is shared between `Pipeline` (reads mode to branch) and a new `dictation` plugin (toggles mode via intent handlers). `DictationProcessor` normalizes punctuation and calls `platform_ops.type_text(text)`. `PlatformOps.type_text` injects keystrokes via `pynput.keyboard.Controller`. Failures swallowed at processor level — pipeline never sees them.

**Tech Stack:** Python 3.11+, `pynput` (already a dependency from MVP push-to-talk), threading, stdlib `re`.

**Depends on:** voice-assistant branch at commit `c137df1` (dictation design spec) or later. Spec: `docs/superpowers/specs/2026-05-20-dictation-mode-design.md`.

---

## File Structure

**New files:**
- `src/voice_assistant/dictation/__init__.py` — empty
- `src/voice_assistant/dictation/mode_store.py` — `ModeStore` (state + Lock)
- `src/voice_assistant/dictation/punctuation.py` — `normalize_punctuation(text) -> str`
- `src/voice_assistant/dictation/processor.py` — `DictationProcessor` (orchestrates normalize → type)
- `src/voice_assistant/executor/plugins/dictation.py` — `start_dictation` / `stop_dictation` plugin handlers
- `tests/unit/dictation/__init__.py` — empty (pytest module disambiguation)
- `tests/unit/dictation/test_mode_store.py`
- `tests/unit/dictation/test_punctuation.py`
- `tests/unit/dictation/test_processor.py`
- `tests/unit/executor/plugins/test_dictation_plugin.py`
- `tests/integration/test_dictation.py`

**Modified files:**
- `src/voice_assistant/config.py` — add `DictationConfig` + `AppConfig.dictation`
- `src/voice_assistant/executor/context.py` — `ExecutorContext.mode_store: ModeStore | None = None`
- `src/voice_assistant/executor/plugins/__init__.py` — register dictation plugin in `register_all()`
- `src/voice_assistant/utils/platform.py` — `PlatformOps.type_text(text)` + lazy pynput import
- `src/voice_assistant/main.py` — `Pipeline.__init__` gains `mode_store` + `dictation_processor`; `process_segment` branches on mode; `_build` constructs both when `cfg.dictation.enabled`; `ExecutorContext` constructed with `mode_store=...`
- `config/commands.yaml` — prepend `start_dictation` / `stop_dictation` intent entries
- `config/default.yaml` — add `dictation` section
- `README.md` — Dictation section + manual checklist
- `tests/unit/test_config.py` — extend with `DictationConfig` tests
- `tests/unit/test_main.py` — extend with Pipeline dictation-branch tests
- `tests/unit/utils/test_platform.py` — extend with `type_text` tests
- `tests/unit/executor/test_context.py` — extend with `mode_store` carrying

No new dependencies — `pynput` already in `pyproject.toml`.

---

## Task 1: `DictationConfig` in `config.py`

**Files:**
- Modify: `src/voice_assistant/config.py`
- Test: extend `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py`:

```python
from voice_assistant.config import DictationConfig


def test_dictation_config_default_values():
    cfg = DictationConfig()
    assert cfg.enabled is True
    assert cfg.type_delay_s == 0.01


def test_dictation_config_accepts_overrides():
    cfg = DictationConfig(enabled=False, type_delay_s=0.05)
    assert cfg.enabled is False
    assert cfg.type_delay_s == 0.05


def test_app_config_has_dictation_section_default_enabled():
    cfg = AppConfig()
    assert cfg.dictation.enabled is True
    assert cfg.dictation.type_delay_s == 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v -k dictation`
Expected: 3 FAILs with `ImportError: cannot import name 'DictationConfig'`.

- [ ] **Step 3: Add `DictationConfig` and wire into `AppConfig`**

Edit `src/voice_assistant/config.py`. After the existing `DialogConfig` class and before `AppConfig`, insert:

```python
class DictationConfig(BaseModel):
    enabled: bool = True
    type_delay_s: float = 0.01
```

Inside `AppConfig`, add the `dictation` field after `dialog`:

```python
dictation: DictationConfig = Field(default_factory=DictationConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -v -k dictation`
Expected: 3 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 3 = 260.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/config.py tests/unit/test_config.py
git commit -m "feat(config): add DictationConfig for dictation mode"
```

---

## Task 2: `ModeStore`

**Files:**
- Create: `src/voice_assistant/dictation/__init__.py` (empty)
- Create: `src/voice_assistant/dictation/mode_store.py`
- Create: `tests/unit/dictation/__init__.py` (empty)
- Create: `tests/unit/dictation/test_mode_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/dictation/test_mode_store.py
import threading
import time

from voice_assistant.dictation.mode_store import ModeStore


def test_default_state_is_command():
    store = ModeStore()
    assert store.is_command() is True
    assert store.is_dictation() is False
    assert store.current_mode() == "command"


def test_start_dictation_switches_to_dictation():
    store = ModeStore()
    store.start_dictation()
    assert store.is_dictation() is True
    assert store.is_command() is False
    assert store.current_mode() == "dictation"


def test_stop_dictation_switches_back_to_command():
    store = ModeStore()
    store.start_dictation()
    store.stop_dictation()
    assert store.is_command() is True
    assert store.is_dictation() is False


def test_start_dictation_is_idempotent():
    store = ModeStore()
    store.start_dictation()
    store.start_dictation()
    assert store.is_dictation() is True


def test_stop_dictation_is_idempotent():
    store = ModeStore()
    store.stop_dictation()
    store.stop_dictation()
    assert store.is_command() is True


def test_concurrent_toggles_do_not_corrupt_state():
    """Smoke test: two threads toggling don't leave the state in a
    weird in-between value."""
    store = ModeStore()
    stop_evt = threading.Event()

    def toggler():
        while not stop_evt.is_set():
            store.start_dictation()
            store.stop_dictation()

    t1 = threading.Thread(target=toggler, daemon=True)
    t2 = threading.Thread(target=toggler, daemon=True)
    t1.start()
    t2.start()
    time.sleep(0.05)
    stop_evt.set()
    t1.join(timeout=1)
    t2.join(timeout=1)
    # Final state must be a valid string mode
    assert store.current_mode() in ("command", "dictation")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/dictation/test_mode_store.py -v`
Expected: 6 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `ModeStore`**

Create `src/voice_assistant/dictation/__init__.py` (empty file).

Create `tests/unit/dictation/__init__.py` (empty file — pytest module disambiguation).

Create `src/voice_assistant/dictation/mode_store.py`:

```python
from __future__ import annotations
import threading


class ModeStore:
    """Thread-safe state machine for assistant operating mode.

    Modes:
      "command"   — default. Pipeline dispatches intents normally.
      "dictation" — Pipeline routes transcripts to DictationProcessor.

    All transitions are idempotent.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mode = "command"

    def is_dictation(self) -> bool:
        with self._lock:
            return self._mode == "dictation"

    def is_command(self) -> bool:
        with self._lock:
            return self._mode == "command"

    def start_dictation(self) -> None:
        with self._lock:
            self._mode = "dictation"

    def stop_dictation(self) -> None:
        with self._lock:
            self._mode = "command"

    def current_mode(self) -> str:
        with self._lock:
            return self._mode
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/dictation/test_mode_store.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 6 = 266.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/dictation/__init__.py src/voice_assistant/dictation/mode_store.py tests/unit/dictation/__init__.py tests/unit/dictation/test_mode_store.py
git commit -m "feat(dictation): ModeStore with thread-safe command/dictation toggle"
```

---

## Task 3: `normalize_punctuation`

**Files:**
- Create: `src/voice_assistant/dictation/punctuation.py`
- Test: `tests/unit/dictation/test_punctuation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/dictation/test_punctuation.py
import pytest

from voice_assistant.dictation.punctuation import normalize_punctuation


def test_empty_string_returns_empty():
    assert normalize_punctuation("") == ""


def test_text_without_punctuation_words_unchanged():
    assert normalize_punctuation("привет мама") == "привет мама"


def test_tochka_becomes_period():
    assert normalize_punctuation("привет мама точка") == "привет мама."


def test_zapyataya_becomes_comma():
    assert normalize_punctuation("молоко запятая хлеб") == "молоко, хлеб"


def test_vopros_becomes_question():
    assert normalize_punctuation("как дела вопрос") == "как дела?"


def test_vosklicatelnyj_becomes_excl():
    assert normalize_punctuation("ого восклицательный") == "ого!"


def test_dvoetochie_becomes_colon():
    assert normalize_punctuation("вывод двоеточие итог") == "вывод: итог"


def test_tire_becomes_em_dash():
    assert normalize_punctuation("а тире б") == "а — б"


def test_defis_becomes_hyphen():
    assert normalize_punctuation("сине дефис зелёный") == "сине - зелёный"


def test_novaya_stroka_becomes_newline():
    assert normalize_punctuation("первая строка новая строка вторая") == \
        "первая строка\nвторая"


def test_multi_word_tochka_s_zapyatoy():
    assert normalize_punctuation("тест точка с запятой следующее") == \
        "тест; следующее"


def test_multi_word_vosklicatelnyj_znak():
    assert normalize_punctuation("ура восклицательный знак") == "ура!"


def test_case_insensitive_match():
    assert normalize_punctuation("Привет Мама ТОЧКА") == "Привет Мама."


def test_word_boundary_prevents_partial_match_vostok():
    """'восток' must not be split into 'вос' + 'ток' via 'точка' substring."""
    assert normalize_punctuation("восток") == "восток"


def test_word_boundary_prevents_partial_match_tochki():
    """'точки' must not match 'точка'."""
    assert normalize_punctuation("не имеет точки") == "не имеет точки"


def test_multiple_punctuation_in_sentence():
    assert normalize_punctuation(
        "молоко запятая хлеб запятая сахар точка") == \
        "молоко, хлеб, сахар."


def test_whitespace_collapse():
    assert normalize_punctuation("привет    мама") == "привет мама"


def test_strip_leading_trailing_spaces():
    assert normalize_punctuation("   привет   ") == "привет"


def test_mixed_russian_english_passthrough():
    assert normalize_punctuation("hello world точка") == "hello world."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/dictation/test_punctuation.py -v`
Expected: 19 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `normalize_punctuation`**

Create `src/voice_assistant/dictation/punctuation.py`:

```python
from __future__ import annotations
import re


_PUNCT: dict[str, str] = {
    # Multi-word phrases must be applied first; we sort by length
    # descending below to handle that.
    "точка с запятой": ";",
    "восклицательный знак": "!",
    "новая строка": "\n",
    # Single-word
    "точка": ".",
    "запятая": ",",
    "вопрос": "?",
    "восклицательный": "!",
    "двоеточие": ":",
    "тире": "—",
    "дефис": "-",
}


def normalize_punctuation(text: str) -> str:
    """Replace Russian punctuation words with their symbols and tighten
    whitespace around the results.

    Word-boundary matching prevents partial-word collisions (e.g.,
    'точки' is NOT replaced — only the exact word 'точка' is).
    """
    if not text:
        return ""
    out = text
    # Longest phrases first so multi-word entries win over single-word.
    for word in sorted(_PUNCT.keys(), key=len, reverse=True):
        symbol = _PUNCT[word]
        out = re.sub(rf"\b{re.escape(word)}\b", symbol, out,
                      flags=re.IGNORECASE)
    # Remove space immediately before standard punctuation.
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    # Tighten newlines.
    out = re.sub(r"\s+\n", "\n", out)
    out = re.sub(r"\n\s+", "\n", out)
    # Collapse runs of horizontal whitespace.
    out = re.sub(r"[ \t]+", " ", out)
    return out.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/dictation/test_punctuation.py -v`
Expected: 19 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 19 = 285.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/dictation/punctuation.py tests/unit/dictation/test_punctuation.py
git commit -m "feat(dictation): normalize_punctuation — Russian words → symbols"
```

---

## Task 4: `PlatformOps.type_text`

**Files:**
- Modify: `src/voice_assistant/utils/platform.py`
- Test: extend `tests/unit/utils/test_platform.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/utils/test_platform.py`:

```python
from unittest.mock import patch, MagicMock


def test_type_text_calls_pynput_controller():
    from voice_assistant.utils.platform import PlatformOps
    ops = PlatformOps()
    with patch("voice_assistant.utils.platform._make_keyboard_controller") as mk:
        ctrl = MagicMock()
        mk.return_value = ctrl
        ops.type_text("hello")
        ctrl.type.assert_called_once_with("hello")


def test_type_text_empty_is_noop():
    from voice_assistant.utils.platform import PlatformOps
    ops = PlatformOps()
    with patch("voice_assistant.utils.platform._make_keyboard_controller") as mk:
        ops.type_text("")
        mk.assert_not_called()


def test_type_text_unicode_passes_through():
    from voice_assistant.utils.platform import PlatformOps
    ops = PlatformOps()
    with patch("voice_assistant.utils.platform._make_keyboard_controller") as mk:
        ctrl = MagicMock()
        mk.return_value = ctrl
        ops.type_text("привет — Hello.")
        ctrl.type.assert_called_once_with("привет — Hello.")


def test_type_text_controller_exception_propagates():
    """type_text should raise on pynput failure; DictationProcessor catches
    upstream."""
    from voice_assistant.utils.platform import PlatformOps
    ops = PlatformOps()
    with patch("voice_assistant.utils.platform._make_keyboard_controller") as mk:
        ctrl = MagicMock()
        ctrl.type.side_effect = RuntimeError("no keyboard")
        mk.return_value = ctrl
        try:
            ops.type_text("hi")
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError to propagate")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/utils/test_platform.py -v -k type_text`
Expected: 4 FAILs with `AttributeError` for missing `_make_keyboard_controller` / `type_text`.

- [ ] **Step 3: Edit `utils/platform.py`**

Add at the top, after existing imports:

```python
from loguru import logger
```

Add a module-level factory helper after the imports (this is the seam tests patch):

```python
def _make_keyboard_controller():
    """Lazy import of pynput.keyboard.Controller; isolated as a function
    so tests can patch it without importing pynput in the test session."""
    from pynput.keyboard import Controller
    return Controller()
```

Add the `type_text` method on `PlatformOps`:

```python
    def type_text(self, text: str) -> None:
        if not text:
            return
        ctrl = _make_keyboard_controller()
        ctrl.type(text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/utils/test_platform.py -v -k type_text`
Expected: 4 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 4 = 289.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/utils/platform.py tests/unit/utils/test_platform.py
git commit -m "feat(platform): type_text for keyboard injection via pynput"
```

---

## Task 5: `DictationProcessor`

**Files:**
- Create: `src/voice_assistant/dictation/processor.py`
- Test: `tests/unit/dictation/test_processor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/dictation/test_processor.py
from unittest.mock import MagicMock

from voice_assistant.dictation.processor import DictationProcessor


def test_type_transcript_normalizes_then_types():
    ops = MagicMock()
    proc = DictationProcessor(platform_ops=ops)
    proc.type_transcript("привет мама точка")
    ops.type_text.assert_called_once_with("привет мама.")


def test_type_transcript_empty_string_no_platform_call():
    ops = MagicMock()
    proc = DictationProcessor(platform_ops=ops)
    proc.type_transcript("")
    ops.type_text.assert_not_called()


def test_type_transcript_whitespace_only_no_platform_call():
    ops = MagicMock()
    proc = DictationProcessor(platform_ops=ops)
    proc.type_transcript("    ")
    ops.type_text.assert_not_called()


def test_type_transcript_swallows_platform_exception():
    """If type_text raises, DictationProcessor does NOT propagate."""
    ops = MagicMock()
    ops.type_text.side_effect = RuntimeError("no keyboard")
    proc = DictationProcessor(platform_ops=ops)
    # Must not raise
    proc.type_transcript("привет")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/dictation/test_processor.py -v`
Expected: 4 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `DictationProcessor`**

Create `src/voice_assistant/dictation/processor.py`:

```python
from __future__ import annotations
from loguru import logger

from voice_assistant.dictation.punctuation import normalize_punctuation


class DictationProcessor:
    """Normalizes punctuation and types the result via platform_ops.

    Failure policy: any exception raised by platform_ops.type_text is
    logged and swallowed — the pipeline never observes typing failures.
    """

    def __init__(self, platform_ops) -> None:
        self._ops = platform_ops

    def type_transcript(self, transcript_text: str) -> None:
        normalized = normalize_punctuation(transcript_text)
        if not normalized:
            return
        try:
            self._ops.type_text(normalized)
        except Exception:
            logger.exception(
                f"dictation type_text failed for {len(normalized)} chars")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/dictation/test_processor.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 4 = 293.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/dictation/processor.py tests/unit/dictation/test_processor.py
git commit -m "feat(dictation): DictationProcessor with normalize → type pipeline"
```

---

## Task 6: Add `mode_store` to `ExecutorContext`

**Files:**
- Modify: `src/voice_assistant/executor/context.py`
- Test: extend `tests/unit/executor/test_context.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/executor/test_context.py`:

```python
def test_executor_context_defaults_mode_store_to_none():
    from voice_assistant.executor.context import ExecutorContext
    from voice_assistant.config import AppConfig
    from unittest.mock import MagicMock

    ctx = ExecutorContext(config=AppConfig(), platform_ops=MagicMock())
    assert ctx.mode_store is None


def test_executor_context_accepts_mode_store():
    from voice_assistant.executor.context import ExecutorContext
    from voice_assistant.config import AppConfig
    from voice_assistant.dictation.mode_store import ModeStore
    from unittest.mock import MagicMock

    store = ModeStore()
    ctx = ExecutorContext(config=AppConfig(), platform_ops=MagicMock(),
                            mode_store=store)
    assert ctx.mode_store is store
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/executor/test_context.py -v -k mode_store`
Expected: 2 FAILs — `ExecutorContext` doesn't accept `mode_store`.

- [ ] **Step 3: Edit `context.py`**

Replace the contents of `src/voice_assistant/executor/context.py` with:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from voice_assistant.config import AppConfig


@dataclass
class ExecutorContext:
    config: AppConfig
    platform_ops: object
    mode_store: Optional[object] = None  # ModeStore | None — avoid circular import

    def resolve_app(self, name: str) -> str:
        return self.config.app_aliases.get(name.strip().lower(), name.strip())

    def resolve_path(self, name: str) -> str:
        return self.config.path_aliases.get(name.strip().lower(), name.strip())

    def resolve_bookmark(self, name: str) -> str | None:
        return self.config.bookmarks.get(name.strip().lower())
```

`mode_store` is typed `object` (not `ModeStore`) to avoid importing `voice_assistant.dictation.mode_store` from `executor.context` and risking a circular import. Plugins that need it can do `from voice_assistant.dictation.mode_store import ModeStore` themselves and `isinstance`-check.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/executor/test_context.py -v -k mode_store`
Expected: 2 PASS.

- [ ] **Step 5: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 2 = 295.

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/executor/context.py tests/unit/executor/test_context.py
git commit -m "feat(executor): ExecutorContext gains optional mode_store"
```

---

## Task 7: Dictation plugin (start/stop handlers)

**Files:**
- Create: `src/voice_assistant/executor/plugins/dictation.py`
- Modify: `src/voice_assistant/executor/plugins/__init__.py`
- Test: `tests/unit/executor/plugins/test_dictation_plugin.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/executor/plugins/test_dictation_plugin.py
from unittest.mock import MagicMock

from voice_assistant.executor.plugins.dictation import (
    _start_dictation, _stop_dictation, register,
)
from voice_assistant.executor.registry import Registry
from voice_assistant.dictation.mode_store import ModeStore


def test_start_dictation_handler_toggles_mode_store():
    ctx = MagicMock()
    store = ModeStore()
    ctx.mode_store = store
    result = _start_dictation({}, ctx)
    assert store.is_dictation() is True
    assert result.success is True
    assert "иктовк" in result.tts_response.lower() or "иктуй" in result.tts_response.lower()


def test_stop_dictation_handler_toggles_mode_store():
    ctx = MagicMock()
    store = ModeStore()
    store.start_dictation()  # pre-condition
    ctx.mode_store = store
    result = _stop_dictation({}, ctx)
    assert store.is_command() is True
    assert result.success is True


def test_start_dictation_with_none_mode_store_returns_fail():
    """When dictation feature is disabled, mode_store is None."""
    ctx = MagicMock()
    ctx.mode_store = None
    result = _start_dictation({}, ctx)
    assert result.success is False
    assert "выключен" in result.message.lower() or "выключен" in result.tts_response.lower()


def test_stop_dictation_with_none_mode_store_is_ok():
    """stop_dictation gracefully no-ops when feature is disabled — user
    already wasn't in dictation, so 'Готово' is the right response."""
    ctx = MagicMock()
    ctx.mode_store = None
    result = _stop_dictation({}, ctx)
    assert result.success is True


def test_register_adds_both_intents():
    reg = Registry()
    register(reg)
    assert "start_dictation" in reg._handlers
    assert "stop_dictation" in reg._handlers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/executor/plugins/test_dictation_plugin.py -v`
Expected: 5 FAILs with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the plugin**

Create `src/voice_assistant/executor/plugins/dictation.py`:

```python
from __future__ import annotations
from voice_assistant.core.types import ExecutionResult
from voice_assistant.executor.registry import Registry


def _start_dictation(slots: dict, ctx) -> ExecutionResult:
    if ctx.mode_store is None:
        return ExecutionResult.fail("Режим диктовки выключен")
    ctx.mode_store.start_dictation()
    return ExecutionResult.ok("Режим диктовки", tts_response="Режим диктовки")


def _stop_dictation(slots: dict, ctx) -> ExecutionResult:
    if ctx.mode_store is not None:
        ctx.mode_store.stop_dictation()
    return ExecutionResult.ok("ok", tts_response="Готово")


def register(reg: Registry) -> None:
    reg.add("start_dictation", _start_dictation)
    reg.add("stop_dictation", _stop_dictation)
```

- [ ] **Step 4: Wire into `register_all`**

Modify `src/voice_assistant/executor/plugins/__init__.py`. Locate the `register_all()` function (it imports and registers each plugin's `register`). Add:

```python
from voice_assistant.executor.plugins import dictation as dictation_plugin
# ... inside register_all ...
dictation_plugin.register(reg)
```

Use the same pattern as the other plugin registrations (apps, browser, etc.).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/executor/plugins/test_dictation_plugin.py -v`
Expected: 5 PASS.

Also extend `tests/unit/executor/test_plugins_register_all.py` if it asserts on a specific intent count — add `start_dictation` and `stop_dictation` to the expected set (read the existing test to find what to update).

- [ ] **Step 6: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 5 = 300 (plus possible adjustments to `test_plugins_register_all`).

- [ ] **Step 7: Commit**

```bash
git add src/voice_assistant/executor/plugins/dictation.py src/voice_assistant/executor/plugins/__init__.py tests/unit/executor/plugins/test_dictation_plugin.py tests/unit/executor/test_plugins_register_all.py
git commit -m "feat(dictation): start_dictation/stop_dictation plugin handlers"
```

---

## Task 8: Add intents to `commands.yaml` + `dictation` to `default.yaml`

**Files:**
- Modify: `config/commands.yaml`
- Modify: `config/default.yaml`

- [ ] **Step 1: Prepend dictation intents to `commands.yaml`**

Open `config/commands.yaml`. At the very top (after the NOTE comment that explains rule ordering, before the first existing intent), insert:

```yaml
- intent: start_dictation
  examples: ["начни диктовать", "режим диктовки", "диктуй"]
  slots: {}
- intent: stop_dictation
  examples: ["стоп диктовка", "конец диктовки", "выход из диктовки", "выход"]
  slots: {}
```

These have literal-token prefixes (`диктуй`, `стоп диктовка`, `режим диктовки`, `конец диктовки`, `выход из диктовки`, `выход`) so they do NOT conflict with the existing `открой {app}` / `закрой {app}` greedy patterns.

- [ ] **Step 2: Add `dictation` section to `config/default.yaml`**

Append:

```yaml
dictation:
  enabled: true
  type_delay_s: 0.01
```

- [ ] **Step 3: Smoke check**

```bash
.\.venv\Scripts\python.exe -c "from voice_assistant.config import load_config; c = load_config('config/default.yaml'); print(c.dictation)"
```
Expected: `enabled=True type_delay_s=0.01`.

Also smoke check that `RulesRouter` parses the updated commands.yaml without errors:

```bash
.\.venv\Scripts\python.exe -c "from voice_assistant.nlu.rules import RulesRouter; r = RulesRouter(commands_path='config/commands.yaml', fuzzy_threshold=85); from voice_assistant.core.types import Transcript; print(r.route(Transcript('режим диктовки', 'ru', 1.0, 100)))"
```
Expected: an `Intent(name='start_dictation', ...)`.

- [ ] **Step 4: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green (no new tests in this task).

- [ ] **Step 5: Commit**

```bash
git add config/commands.yaml config/default.yaml
git commit -m "chore: add dictation intents + config section"
```

---

## Task 9: Wire dictation into `Pipeline` + `_build`

**Files:**
- Modify: `src/voice_assistant/main.py`
- Test: extend `tests/unit/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_main.py`:

```python
def test_pipeline_constructor_accepts_mode_store_and_processor():
    from voice_assistant.main import Pipeline
    from voice_assistant.dictation.mode_store import ModeStore
    from voice_assistant.dictation.processor import DictationProcessor
    store = ModeStore()
    proc = DictationProcessor(platform_ops=MagicMock())
    pipe = Pipeline(
        config=AppConfig(), asr=MagicMock(), nlu=MagicMock(),
        registry=MagicMock(), ctx=MagicMock(), feedback=MagicMock(),
        mode_store=store, dictation_processor=proc,
    )
    assert pipe.mode_store is store
    assert pipe.dictation_processor is proc


def test_pipeline_in_dictation_mode_routes_to_processor():
    """Non-stop intent during dictation → DictationProcessor.type_transcript."""
    from voice_assistant.main import Pipeline
    from voice_assistant.core.types import (
        AudioSegment, Transcript, Intent, ExecutionResult,
    )
    from voice_assistant.dictation.mode_store import ModeStore
    import numpy as np

    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("привет мама точка", "ru", 0.95, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("unknown", {}, 0.0)
    registry = MagicMock()
    feedback = MagicMock()
    store = ModeStore()
    store.start_dictation()
    proc = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                     ctx=MagicMock(), feedback=feedback,
                     mode_store=store, dictation_processor=proc)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    proc.type_transcript.assert_called_once_with("привет мама точка")
    registry.dispatch.assert_not_called()


def test_pipeline_in_dictation_mode_with_stop_intent_dispatches():
    """stop_dictation during dictation → registry.dispatch (plugin toggles mode)."""
    from voice_assistant.main import Pipeline
    from voice_assistant.core.types import (
        AudioSegment, Transcript, Intent, ExecutionResult,
    )
    from voice_assistant.dictation.mode_store import ModeStore
    import numpy as np

    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("стоп диктовка", "ru", 0.95, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("stop_dictation", {}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult.ok("ok",
                                                         tts_response="Готово")
    feedback = MagicMock()
    store = ModeStore()
    store.start_dictation()
    proc = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                     ctx=MagicMock(), feedback=feedback,
                     mode_store=store, dictation_processor=proc)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    registry.dispatch.assert_called_once()
    proc.type_transcript.assert_not_called()
    feedback.emit.assert_called_once_with("Готово", success=True)


def test_pipeline_in_command_mode_unchanged():
    """When NOT in dictation, existing flow runs."""
    from voice_assistant.main import Pipeline
    from voice_assistant.core.types import (
        AudioSegment, Transcript, Intent, ExecutionResult,
    )
    from voice_assistant.dictation.mode_store import ModeStore
    import numpy as np

    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой блокнот", "ru", 0.95, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "блокнот"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = ExecutionResult.ok("ok",
                                                         tts_response="Открыл")
    feedback = MagicMock()
    store = ModeStore()  # default: command
    proc = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                     ctx=MagicMock(), feedback=feedback,
                     mode_store=store, dictation_processor=proc)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    registry.dispatch.assert_called_once()
    proc.type_transcript.assert_not_called()


def test_build_constructs_mode_store_and_processor_when_dictation_enabled(
        tmp_path, monkeypatch):
    from voice_assistant.dictation.mode_store import ModeStore
    from voice_assistant.dictation.processor import DictationProcessor

    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    monkeypatch.setattr("voice_assistant.main.SystemTray", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n"
        "tray:\n  enabled: false\n"
        "dialog:\n  enabled: false\n"
        "dictation:\n  enabled: true\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback, tray = _build(
        str(tmp_path / "default.yaml"))
    assert isinstance(pipe.mode_store, ModeStore)
    assert isinstance(pipe.dictation_processor, DictationProcessor)


def test_build_skips_mode_store_when_dictation_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr("voice_assistant.main.FasterWhisperEngine", MagicMock())
    monkeypatch.setattr("voice_assistant.main.AudioCapture", MagicMock())
    monkeypatch.setattr("voice_assistant.main.PushToTalk", MagicMock())
    monkeypatch.setattr("voice_assistant.main.VADSegmenter", MagicMock())
    monkeypatch.setattr("voice_assistant.main.register_all", MagicMock())
    monkeypatch.setattr("voice_assistant.main.setup_logging", MagicMock())
    monkeypatch.setattr("voice_assistant.main.SystemTray", MagicMock())

    (tmp_path / "commands.yaml").write_text(
        '- intent: noop\n  examples: ["noop"]\n  slots: {}\n',
        encoding="utf-8")
    (tmp_path / "default.yaml").write_text(
        "tts:\n  enabled: false\n"
        "llm:\n  enabled: false\n"
        "wake:\n  enabled: false\n"
        "tray:\n  enabled: false\n"
        "dialog:\n  enabled: false\n"
        "dictation:\n  enabled: false\n",
        encoding="utf-8")

    from voice_assistant.main import _build
    pipe, qs, capture, ptt, vad, feedback, tray = _build(
        str(tmp_path / "default.yaml"))
    assert pipe.mode_store is None
    assert pipe.dictation_processor is None
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "mode_store or dictation"`
Expected: FAILs — Pipeline doesn't accept the new kwargs, `_build` doesn't construct.

- [ ] **Step 3: Edit `main.py` — imports and `Pipeline`**

a) Add imports near the top of `main.py`:

```python
from voice_assistant.dictation.mode_store import ModeStore
from voice_assistant.dictation.processor import DictationProcessor
```

b) Find `Pipeline.__init__` signature (currently with `context_store`):

```python
class Pipeline:
    def __init__(self, config: AppConfig, asr: ASREngine, nlu: NLURouter,
                 registry: Registry, ctx: ExecutorContext,
                 feedback: FeedbackSink,
                 context_store: ContextStore | None = None):
```

Replace with:

```python
class Pipeline:
    def __init__(self, config: AppConfig, asr: ASREngine, nlu: NLURouter,
                 registry: Registry, ctx: ExecutorContext,
                 feedback: FeedbackSink,
                 context_store: ContextStore | None = None,
                 mode_store: ModeStore | None = None,
                 dictation_processor: DictationProcessor | None = None):
```

c) Inside `__init__`, after `self.context_store = context_store`, add:

```python
        self.mode_store = mode_store
        self.dictation_processor = dictation_processor
```

d) Replace the `process_segment` body. Find it and replace whole-method (preserve the existing ASR confidence/empty gate, NLU route, and the existing command-mode flow). The new body:

```python
    def process_segment(self, segment: AudioSegment) -> None:
        transcript = self.asr.transcribe(segment)
        if self.config.store_transcripts:
            logger.info(f"ASR: '{transcript.text}' "
                        f"(conf={transcript.confidence:.2f})")
        else:
            logger.info(f"ASR conf={transcript.confidence:.2f} "
                        f"(transcript redacted)")
        if transcript.confidence < self.config.asr.min_confidence \
                or not transcript.text.strip():
            self.feedback.emit("Не понял, повтори", success=False)
            return

        intent = self.nlu.route(transcript)

        # Dictation branch
        if self.mode_store is not None and self.mode_store.is_dictation():
            if intent.name == "stop_dictation":
                result = self.registry.dispatch(intent, self.ctx)
                self.feedback.emit(result.tts_response,
                                    success=result.success)
                return
            if self.dictation_processor is not None:
                self.dictation_processor.type_transcript(transcript.text)
            logger.info(f"dictated: {len(transcript.text)} chars")
            return

        # Command branch (existing)
        if intent.name == "unknown":
            self.feedback.emit("Не понял, повтори", success=False)
            return
        result = self.registry.dispatch(intent, self.ctx)
        logger.info(f"intent={intent.name} success={result.success}")
        if result.success and self.context_store is not None:
            self.context_store.add(intent)
        self.feedback.emit(result.tts_response, success=result.success)
```

- [ ] **Step 4: Edit `main.py` — `_build` and `ExecutorContext`**

a) In `_build`, find where `ExecutorContext` is constructed (currently `ctx = ExecutorContext(config=cfg, platform_ops=ops)`). It must now also carry `mode_store`.

b) Add the dictation construction near the top of `_build` (BEFORE the executor context is built so `mode_store` can be passed). After `ops = get_platform_ops()`, insert:

```python
    mode_store: ModeStore | None = None
    dictation_processor: DictationProcessor | None = None
    if cfg.dictation.enabled:
        mode_store = ModeStore()
        dictation_processor = DictationProcessor(platform_ops=ops)
```

c) Update the `ExecutorContext(...)` line:

```python
    ctx = ExecutorContext(config=cfg, platform_ops=ops, mode_store=mode_store)
```

d) Update the `Pipeline(...)` construction. Find:

```python
    pipe = Pipeline(cfg, asr, nlu, global_registry(), ctx, feedback,
                     context_store=context_store)
```

Replace with:

```python
    pipe = Pipeline(cfg, asr, nlu, global_registry(), ctx, feedback,
                     context_store=context_store,
                     mode_store=mode_store,
                     dictation_processor=dictation_processor)
```

- [ ] **Step 5: Run new tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -v -k "mode_store or dictation"`
Expected: 6 PASS.

- [ ] **Step 6: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 6 = 306. **Watch for regressions** — the `process_segment` rewrite is delicate. Specifically:

- Pre-existing tests like `test_pipeline_processes_one_segment_end_to_end` rely on the command-mode flow being unchanged. They construct `Pipeline` without `mode_store` (default `None`), so the dictation branch is skipped — they should still pass.
- The store_transcripts log behaviour from earlier work must be preserved verbatim.

If something breaks, the rewrite probably altered the ordering or the `mode_store is not None` guard. Re-check against the spec.

- [ ] **Step 7: Commit**

```bash
git add src/voice_assistant/main.py tests/unit/test_main.py
git commit -m "feat(main): Pipeline dictation branch + _build wiring"
```

---

## Task 10: Integration test

**Files:**
- Create: `tests/integration/test_dictation.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_dictation.py
"""End-to-end dictation test.

Real RulesRouter + ModeStore + DictationProcessor + plugins; mocks ASR
and platform_ops. Verifies the 3-turn flow:
  1. "режим диктовки"      → mode flips to dictation
  2. "привет мама точка"   → ops.type_text("привет мама.")
  3. "стоп диктовка"        → mode flips back to command
"""
import numpy as np
from unittest.mock import MagicMock

from voice_assistant.config import AppConfig
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.executor.plugins import dictation as dictation_plugin
from voice_assistant.dictation.mode_store import ModeStore
from voice_assistant.dictation.processor import DictationProcessor
from voice_assistant.core.types import AudioSegment, Transcript
from voice_assistant.main import Pipeline


def test_three_turn_dictation_flow(tmp_path):
    cmds = tmp_path / "commands.yaml"
    cmds.write_text(
        '- intent: start_dictation\n'
        '  examples: ["режим диктовки", "диктуй"]\n'
        '  slots: {}\n'
        '- intent: stop_dictation\n'
        '  examples: ["стоп диктовка", "конец диктовки"]\n'
        '  slots: {}\n',
        encoding="utf-8")

    cfg = AppConfig()
    asr = MagicMock()
    nlu = RulesRouter(commands_path=cmds, fuzzy_threshold=85)
    reg = Registry()
    dictation_plugin.register(reg)
    ops = MagicMock()
    store = ModeStore()
    proc = DictationProcessor(platform_ops=ops)
    ctx = ExecutorContext(config=cfg, platform_ops=ops, mode_store=store)
    feedback = MagicMock()

    pipe = Pipeline(cfg, asr, nlu, reg, ctx, feedback,
                     mode_store=store, dictation_processor=proc)

    # Turn 1: enter dictation
    asr.transcribe.return_value = Transcript("режим диктовки", "ru", 0.95, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    assert store.is_dictation() is True
    ops.type_text.assert_not_called()  # not yet — we just toggled mode

    # Turn 2: dictate
    asr.transcribe.return_value = Transcript(
        "привет мама точка", "ru", 0.95, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    ops.type_text.assert_called_once_with("привет мама.")

    # Turn 3: exit dictation
    asr.transcribe.return_value = Transcript("стоп диктовка", "ru", 0.95, 500)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))
    assert store.is_command() is True
```

- [ ] **Step 2: Run the integration test**

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_dictation.py -v`
Expected: PASS.

If `ops.type_text` is not called with "привет мама." in turn 2, investigate:
- Did mode_store toggle on turn 1? Add `print(store.current_mode())` after each turn.
- Did NLU return `unknown` for "привет мама точка"? (Should — no rule matches; that's intended.)
- Did `process_segment` reach the dictation branch? Check via log output.

- [ ] **Step 3: Run full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green. Total = previous + 1 = 307.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_dictation.py
git commit -m "test: integration test for 3-turn dictation flow"
```

---

## Task 11: README + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append Dictation section + manual checklist**

Below the existing "Multi-turn dialog verification checklist", append:

```markdown

## Dictation mode (надиктовка)

Скажи "режим диктовки" / "начни диктовать" / "диктуй" — ассистент перейдёт в режим диктовки. Дальше всё, что ты говоришь, печатается в активное окно (документ, email, чат). Знаки препинания произноси словами: `точка, запятая, вопрос, восклицательный, двоеточие, тире, дефис, точка с запятой, новая строка`.

Чтобы выйти: "стоп диктовка" / "конец диктовки" / "выход".

Пример:
```
ты: режим диктовки
ассистент: Режим диктовки

ты:  привет мама точка как у тебя дела вопрос
напечатано: привет мама. как у тебя дела?

ты: стоп диктовка
ассистент: Готово
```

Отключить весь режим: `dictation.enabled: false` в `config/default.yaml` (фраза "режим диктовки" будет давать "Режим диктовки выключен").

## Dictation verification checklist

- [ ] "режим диктовки" → TTS подтверждает + переход в dictation
- [ ] "привет всем точка" → "привет всем." напечатано в активном Notepad
- [ ] "новая строка" → перевод строки
- [ ] "сколько времени вопрос" → "сколько времени?"
- [ ] "молоко запятая хлеб запятая сахар" → "молоко, хлеб, сахар"
- [ ] "стоп диктовка" → выход, обычные команды снова работают
- [ ] Длинная фраза 50+ слов печатается полностью
- [ ] `dictation.enabled: false` → "режим диктовки" не активирует mode (TTS говорит "Режим диктовки выключен")
- [ ] Multi-turn context НЕ обновляется во время диктовки (после "стоп" "закрой его" даёт "Не понял")
```

- [ ] **Step 2: Run full test suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all green at 307.

- [ ] **Step 3: Coverage check**

Run: `.\.venv\Scripts\python.exe -m pytest --cov=voice_assistant --cov-report=term-missing -q`
Expected: new modules at ≥80%:
- `dictation/mode_store.py` — should approach 100%
- `dictation/punctuation.py` — should approach 100% (pure function)
- `dictation/processor.py` — should be 100%
- `executor/plugins/dictation.py` — should approach 100%
- `utils/platform.py` — `type_text` adds ~5 lines, likely still around 60-70% overall (rest of file is hardware-touching).

Note any module below 80% in your commit message.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: dictation mode setup notes + manual checklist"
```

---

## Self-Review Notes

- **Spec coverage:**
  - `DictationConfig` (T1)
  - `ModeStore` (T2)
  - `normalize_punctuation` (T3)
  - `PlatformOps.type_text` (T4)
  - `DictationProcessor` (T5)
  - `ExecutorContext.mode_store` (T6)
  - `start_dictation/stop_dictation` plugin handlers (T7)
  - `commands.yaml` + `default.yaml` updates (T8)
  - `Pipeline` dictation branch + `_build` wiring (T9)
  - Integration test (T10)
  - README + manual checklist (T11)

  All spec §7 failure modes covered: type_text raise (T5 test), mode_store=None (T7 test), empty transcript (T5 test), idempotent toggles (T2 test), platform abstraction failures (T4 test).

- **Task ordering:**
  - T2 (ModeStore) before T6 (ExecutorContext uses it) and T7 (plugin uses it).
  - T3 (punctuation) before T5 (processor uses it).
  - T4 (type_text) before T5 (processor calls it through platform_ops).
  - T5 (processor) before T9 (Pipeline uses it).
  - T6 (ExecutorContext) before T7 (plugin reads ctx.mode_store).
  - T7 (plugin) before T8 (yaml references the intents — though yaml is just data, it doesn't fail without the plugin).
  - T8 (yaml + commands) before T9 (Pipeline tests don't need yaml, but the integration test in T10 does).
  - T9 (Pipeline wiring) before T10 (integration test).

- **Type consistency:**
  - `ModeStore(no args)` — used identically everywhere.
  - `DictationProcessor(platform_ops=...)` — matches T5 declaration and T9 call site.
  - `ExecutorContext(config, platform_ops, mode_store=None)` — matches T6, T9, integration test.
  - `Pipeline(..., mode_store=None, dictation_processor=None)` — matches T9.
  - Plugin handler signature `(slots: dict, ctx) -> ExecutionResult` — matches other plugins.

- **Out of scope** (per spec §11): auto-capitalize, dictation+multi-turn merge, per-app punctuation profiles, click-to-target, continuous streaming.

- **Test density:** ~53 new tests (3 config + 6 mode_store + 19 punctuation + 4 platform + 4 processor + 2 context + 5 plugin + 6 main + 1 integration + register_all delta + tests of yaml interaction = ~50). Expected total after T11: ~307 (current 257 + ~50).
