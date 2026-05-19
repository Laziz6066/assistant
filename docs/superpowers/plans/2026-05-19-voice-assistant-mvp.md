# Voice PC Assistant — MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP voice assistant: push-to-talk capture → VAD → faster-whisper ASR → rules NLU → plugin executor → CLI feedback, running on Windows.

**Architecture:** Threads connected by `queue.Queue` (one thread per pipeline stage). Immutable dataclass DTOs cross queue boundaries. Abstract interfaces (`ASREngine`, `NLURouter`, `Activator`, `FeedbackSink`) so later stages swap implementations. Plugins register via `@register_intent` decorator; platform ops hidden behind `utils/platform.py`.

**Tech Stack:** Python 3.11+, faster-whisper (CUDA/int8_float16), silero-vad, sounddevice, pynput, pygetwindow, pydantic v2, pydantic-settings, PyYAML, rapidfuzz, loguru, plyer, pytest.

---

## File Structure

```
voice_assistant/
├── pyproject.toml
├── .env.example
├── config/default.yaml
├── config/commands.yaml
├── src/voice_assistant/
│   ├── __init__.py
│   ├── main.py                       # pipeline assembly + graceful shutdown
│   ├── config.py                     # pydantic models + YAML loader
│   ├── core/__init__.py
│   ├── core/types.py                 # frozen DTOs: AudioSegment, Transcript, Intent, ExecutionResult
│   ├── core/queues.py                # PipelineQueues + STOP sentinel
│   ├── utils/__init__.py
│   ├── utils/logging.py              # loguru setup
│   ├── utils/platform.py             # Windows ops behind interface
│   ├── audio/__init__.py
│   ├── audio/capture.py              # sounddevice + ring buffer thread
│   ├── audio/vad.py                  # silero-vad segmenter
│   ├── activation/__init__.py
│   ├── activation/base.py            # Activator interface
│   ├── activation/hotkey.py          # push-to-talk (pynput)
│   ├── asr/__init__.py
│   ├── asr/base.py                   # ASREngine interface
│   ├── asr/faster_whisper_engine.py
│   ├── nlu/__init__.py
│   ├── nlu/base.py                   # NLURouter interface
│   ├── nlu/rules.py                  # regex + rapidfuzz matcher
│   ├── executor/__init__.py
│   ├── executor/result.py            # re-export ExecutionResult helper
│   ├── executor/registry.py          # @register_intent + dispatch
│   ├── executor/plugins/__init__.py  # imports all plugins (registration)
│   ├── executor/plugins/apps.py
│   ├── executor/plugins/windows.py
│   ├── executor/plugins/browser.py
│   ├── executor/plugins/files.py
│   ├── executor/plugins/clipboard.py
│   └── executor/plugins/system.py
├── scripts/benchmark_asr.py
└── tests/
    ├── conftest.py
    ├── unit/ (mirrors src)
    ├── integration/test_pipeline.py
    └── fixtures/audio/.gitkeep
```

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/voice_assistant/__init__.py`, `tests/conftest.py`, `tests/fixtures/audio/.gitkeep`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "voice-assistant"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "faster-whisper>=1.0",
  "silero-vad>=5.0",
  "sounddevice>=0.4",
  "numpy",
  "pynput",
  "pygetwindow; platform_system=='Windows'",
  "pywin32; platform_system=='Windows'",
  "rapidfuzz",
  "pydantic>=2",
  "pydantic-settings",
  "pyyaml",
  "loguru",
  "plyer",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov", "pytest-mock"]

[project.scripts]
voice-assistant = "voice_assistant.main:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = ["windows: requires Windows platform"]
```

- [ ] **Step 2: Create `.env.example`**

```
# Optional overrides. Real .env is gitignored.
VA_ASR__MODEL=medium
VA_LOG_LEVEL=INFO
```

- [ ] **Step 3: Create `src/voice_assistant/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

- [ ] **Step 5: Create empty `tests/fixtures/audio/.gitkeep`**

Empty file.

- [ ] **Step 6: Install dev deps and verify pytest runs**

Run: `pip install -e ".[dev]"` then `pytest -q`
Expected: pytest collects 0 tests, exits 0.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .env.example src/voice_assistant/__init__.py tests/conftest.py tests/fixtures/audio/.gitkeep
git commit -m "chore: project scaffold for voice assistant MVP"
```

---

## Task 2: Core DTOs

**Files:**
- Create: `src/voice_assistant/core/__init__.py`, `src/voice_assistant/core/types.py`
- Test: `tests/unit/core/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/core/test_types.py
import dataclasses
import numpy as np
import pytest
from voice_assistant.core.types import AudioSegment, Transcript, Intent, ExecutionResult


def test_dtos_are_frozen():
    t = Transcript(text="hi", language="ru", confidence=0.9, duration_ms=120)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.text = "bye"


def test_intent_unknown_helper():
    i = Intent.unknown()
    assert i.name == "unknown"
    assert i.slots == {}
    assert i.confidence == 0.0


def test_audio_segment_holds_samples():
    samples = np.zeros(1600, dtype=np.int16)
    seg = AudioSegment(samples=samples, sample_rate=16000)
    assert seg.duration_ms == 100


def test_execution_result_ok_and_fail():
    ok = ExecutionResult.ok("done", tts_response="готово")
    assert ok.success is True and ok.tts_response == "готово"
    fail = ExecutionResult.fail("boom")
    assert fail.success is False and fail.message == "boom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/core/test_types.py -v`
Expected: FAIL with `ModuleNotFoundError: voice_assistant.core.types`

- [ ] **Step 3: Create `src/voice_assistant/core/__init__.py`**

Empty file.

- [ ] **Step 4: Write `src/voice_assistant/core/types.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass(frozen=True)
class AudioSegment:
    samples: np.ndarray  # int16 mono
    sample_rate: int

    @property
    def duration_ms(self) -> int:
        return int(len(self.samples) * 1000 / self.sample_rate)


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    confidence: float
    duration_ms: int


@dataclass(frozen=True)
class Intent:
    name: str
    slots: dict = field(default_factory=dict)
    confidence: float = 1.0

    @classmethod
    def unknown(cls) -> "Intent":
        return cls(name="unknown", slots={}, confidence=0.0)


@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    message: str
    tts_response: str = ""

    @classmethod
    def ok(cls, message: str, tts_response: str = "") -> "ExecutionResult":
        return cls(success=True, message=message, tts_response=tts_response or message)

    @classmethod
    def fail(cls, message: str, tts_response: str = "") -> "ExecutionResult":
        return cls(success=False, message=message, tts_response=tts_response or message)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/core/test_types.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/core tests/unit/core/test_types.py
git commit -m "feat: core immutable DTOs"
```

---

## Task 3: Config (pydantic + YAML)

**Files:**
- Create: `src/voice_assistant/config.py`, `config/default.yaml`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config.py
import textwrap
import pytest
from voice_assistant.config import load_config, AppConfig


def test_load_defaults(tmp_path):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text(textwrap.dedent("""
        asr: {model: medium, device: cuda}
        hotkey: {push_to_talk: ctrl_r}
        app_aliases: {телега: telegram}
    """), encoding="utf-8")
    cfg = load_config(cfg_file)
    assert isinstance(cfg, AppConfig)
    assert cfg.asr.model == "medium"
    assert cfg.asr.device == "cuda"
    assert cfg.app_aliases["телега"] == "telegram"
    assert cfg.audio.sample_rate == 16000  # default


def test_invalid_yaml_raises(tmp_path):
    cfg_file = tmp_path / "c.yaml"
    cfg_file.write_text("asr: {device: 12345}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(cfg_file)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: voice_assistant.config`

- [ ] **Step 3: Write `src/voice_assistant/config.py`**

```python
from __future__ import annotations
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ValidationError, Field


class AudioConfig(BaseModel):
    input_device: int | None = None
    sample_rate: int = 16000
    ring_seconds: float = 30.0


class ASRConfig(BaseModel):
    engine: str = "faster-whisper"
    model: str = "medium"
    language: str = "ru"
    device: Literal["auto", "cpu", "cuda"] = "cuda"
    compute_type: str = "int8_float16"
    min_confidence: float = 0.4


class VADConfig(BaseModel):
    threshold: float = 0.5
    min_speech_ms: int = 300
    max_speech_ms: int = 15000


class HotkeyConfig(BaseModel):
    push_to_talk: str = "ctrl_r"


class NLUConfig(BaseModel):
    fuzzy_threshold: int = 85


class AppConfig(BaseModel):
    audio: AudioConfig = Field(default_factory=AudioConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    nlu: NLUConfig = Field(default_factory=NLUConfig)
    log_level: str = "INFO"
    store_transcripts: bool = False
    app_aliases: dict[str, str] = Field(default_factory=dict)
    bookmarks: dict[str, str] = Field(default_factory=dict)
    path_aliases: dict[str, str] = Field(default_factory=dict)


def load_config(path: str | Path) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    try:
        return AppConfig(**raw)
    except ValidationError as e:
        raise ValueError(f"Invalid config: {e}") from e
```

- [ ] **Step 4: Create `config/default.yaml`**

```yaml
audio:
  input_device: null
  sample_rate: 16000
asr:
  engine: faster-whisper
  model: medium
  language: ru
  device: cuda
  compute_type: int8_float16
  min_confidence: 0.4
vad:
  threshold: 0.5
  min_speech_ms: 300
  max_speech_ms: 15000
hotkey:
  push_to_talk: ctrl_r
nlu:
  fuzzy_threshold: 85
log_level: INFO
store_transcripts: false
app_aliases:
  телеграм: telegram
  телега: telegram
  браузер: firefox
  код: code
bookmarks:
  ютуб: https://youtube.com
path_aliases:
  загрузки: "~/Downloads"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/config.py config/default.yaml tests/unit/test_config.py
git commit -m "feat: pydantic config with YAML loader"
```

---

## Task 4: Logging utility

**Files:**
- Create: `src/voice_assistant/utils/__init__.py`, `src/voice_assistant/utils/logging.py`
- Test: `tests/unit/utils/test_logging.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/utils/test_logging.py
from voice_assistant.utils.logging import setup_logging


def test_setup_logging_returns_logger_and_respects_level():
    log = setup_logging(level="WARNING")
    assert log is not None
    log.warning("test-message")  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/utils/test_logging.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/voice_assistant/utils/__init__.py`**

Empty file.

- [ ] **Step 4: Write `src/voice_assistant/utils/logging.py`**

```python
from __future__ import annotations
import sys
from loguru import logger


def setup_logging(level: str = "INFO", logfile: str | None = "voice_assistant.log"):
    logger.remove()
    logger.add(sys.stderr, level=level, enqueue=True)
    if logfile:
        logger.add(logfile, level=level, rotation="10 MB", enqueue=True)
    return logger
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/utils/test_logging.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/utils/__init__.py src/voice_assistant/utils/logging.py tests/unit/utils/test_logging.py
git commit -m "feat: loguru logging setup"
```

---

## Task 5: Platform abstraction (Windows)

**Files:**
- Create: `src/voice_assistant/utils/platform.py`
- Test: `tests/unit/utils/test_platform.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/utils/test_platform.py
from unittest.mock import patch
from voice_assistant.utils.platform import PlatformOps, get_platform_ops


def test_get_platform_ops_returns_instance():
    ops = get_platform_ops()
    assert isinstance(ops, PlatformOps)


def test_launch_app_calls_subprocess(monkeypatch):
    ops = get_platform_ops()
    called = {}
    monkeypatch.setattr(ops, "_spawn", lambda cmd: called.setdefault("cmd", cmd))
    ops.launch_app("notepad")
    assert called["cmd"] == "notepad"


def test_open_path_expands_user(monkeypatch):
    ops = get_platform_ops()
    seen = {}
    monkeypatch.setattr(ops, "_open", lambda p: seen.setdefault("p", p))
    ops.open_path("~")
    assert "~" not in seen["p"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/utils/test_platform.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/utils/platform.py`**

```python
from __future__ import annotations
import os
import platform
import shutil
import subprocess
from pathlib import Path


class PlatformOps:
    """Windows implementation. Linux/macOS deferred to Release stage."""

    def _spawn(self, cmd: str) -> None:
        subprocess.Popen(cmd, shell=True)

    def _open(self, path: str) -> None:
        os.startfile(path)  # type: ignore[attr-defined]

    def launch_app(self, name: str) -> None:
        exe = shutil.which(name) or name
        self._spawn(exe)

    def close_app(self, name: str) -> None:
        subprocess.run(["taskkill", "/IM", f"{name}.exe", "/F"],
                        capture_output=True, check=False)

    def open_path(self, path: str) -> None:
        self._open(str(Path(os.path.expanduser(path))))

    def set_volume(self, percent: int) -> None:
        # nircmd-style fallback via PowerShell SendKeys is unreliable;
        # use pycaw if available, else no-op with raise for caller to handle.
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


def get_platform_ops() -> PlatformOps:
    if platform.system() != "Windows":
        raise NotImplementedError("Only Windows is supported in MVP")
    return PlatformOps()
```

- [ ] **Step 4: Add `pycaw` to deps**

Modify `pyproject.toml` dependencies: add `"pycaw; platform_system=='Windows'"` and `"comtypes; platform_system=='Windows'"`. Run `pip install -e ".[dev]"`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/utils/test_platform.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/utils/platform.py pyproject.toml tests/unit/utils/test_platform.py
git commit -m "feat: Windows platform operations abstraction"
```

---

## Task 6: Pipeline queues + STOP sentinel

**Files:**
- Create: `src/voice_assistant/core/queues.py`
- Test: `tests/unit/core/test_queues.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/core/test_queues.py
from voice_assistant.core.queues import PipelineQueues, STOP


def test_queues_exist_and_stop_is_singleton():
    q = PipelineQueues()
    assert q.speech_q is not None
    assert q.asr_q is not None
    assert q.nlu_q is not None
    assert q.exec_q is not None
    q.speech_q.put(STOP)
    assert q.speech_q.get() is STOP
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/core/test_queues.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/core/queues.py`**

```python
from __future__ import annotations
import queue
from dataclasses import dataclass, field


class _Stop:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<STOP>"


STOP = _Stop()


@dataclass
class PipelineQueues:
    speech_q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
    asr_q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
    nlu_q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
    exec_q: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=8))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/core/test_queues.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/voice_assistant/core/queues.py tests/unit/core/test_queues.py
git commit -m "feat: pipeline queues and STOP sentinel"
```

---

## Task 7: Audio capture (ring buffer)

**Files:**
- Create: `src/voice_assistant/audio/__init__.py`, `src/voice_assistant/audio/capture.py`
- Test: `tests/unit/audio/test_capture.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/audio/test_capture.py
import numpy as np
from voice_assistant.audio.capture import RingBuffer


def test_ring_buffer_keeps_last_n_samples():
    rb = RingBuffer(capacity=5)
    rb.extend(np.array([1, 2, 3], dtype=np.int16))
    rb.extend(np.array([4, 5, 6, 7], dtype=np.int16))
    out = rb.snapshot()
    assert list(out) == [3, 4, 5, 6, 7]


def test_ring_buffer_empty_snapshot():
    rb = RingBuffer(capacity=4)
    assert len(rb.snapshot()) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/audio/test_capture.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/voice_assistant/audio/__init__.py`**

Empty file.

- [ ] **Step 4: Write `src/voice_assistant/audio/capture.py`**

```python
from __future__ import annotations
import threading
import numpy as np
from loguru import logger


class RingBuffer:
    def __init__(self, capacity: int):
        self._cap = capacity
        self._buf = np.zeros(0, dtype=np.int16)
        self._lock = threading.Lock()

    def extend(self, chunk: np.ndarray) -> None:
        with self._lock:
            self._buf = np.concatenate([self._buf, chunk])[-self._cap:]

    def snapshot(self) -> np.ndarray:
        with self._lock:
            return self._buf.copy()


class AudioCapture:
    """Continuously records mic into a ring buffer. Thread-based."""

    def __init__(self, sample_rate: int, ring_seconds: float, device: int | None):
        self.sample_rate = sample_rate
        self.device = device
        self.ring = RingBuffer(int(sample_rate * ring_seconds))
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        def _cb(indata, frames, time, status):
            if status:
                logger.warning(f"audio status: {status}")
            self.ring.extend(indata[:, 0].copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate, channels=1, dtype="int16",
                device=self.device, callback=_cb)
            self._stream.start()
        except Exception as e:
            logger.error(f"Cannot open microphone: {e}")
            raise

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/audio/test_capture.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/audio/__init__.py src/voice_assistant/audio/capture.py tests/unit/audio/test_capture.py
git commit -m "feat: audio capture with ring buffer"
```

---

## Task 8: VAD segmenter

**Files:**
- Create: `src/voice_assistant/audio/vad.py`
- Test: `tests/unit/audio/test_vad.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/audio/test_vad.py
import numpy as np
from voice_assistant.audio.vad import VADSegmenter


class FakeVADModel:
    """Returns speech prob 0.9 for non-zero frames, 0.0 for silence."""
    def __call__(self, tensor, sr):
        import numpy as np
        arr = tensor.numpy() if hasattr(tensor, "numpy") else np.asarray(tensor)
        return type("T", (), {"item": lambda s: 0.9 if np.any(arr != 0) else 0.0})()


def test_rejects_too_short(monkeypatch):
    seg = VADSegmenter(sample_rate=16000, threshold=0.5,
                        min_speech_ms=300, max_speech_ms=15000,
                        model=FakeVADModel())
    samples = np.ones(1600, dtype=np.int16)  # 100ms < 300ms
    assert seg.segment(samples) is None


def test_accepts_valid_segment(monkeypatch):
    seg = VADSegmenter(sample_rate=16000, threshold=0.5,
                        min_speech_ms=300, max_speech_ms=15000,
                        model=FakeVADModel())
    samples = np.ones(16000, dtype=np.int16)  # 1000ms
    out = seg.segment(samples)
    assert out is not None
    assert out.sample_rate == 16000


def test_trims_too_long(monkeypatch):
    seg = VADSegmenter(sample_rate=16000, threshold=0.5,
                        min_speech_ms=300, max_speech_ms=15000,
                        model=FakeVADModel())
    samples = np.ones(16000 * 20, dtype=np.int16)  # 20s
    out = seg.segment(samples)
    assert out is not None
    assert out.duration_ms <= 15000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/audio/test_vad.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/audio/vad.py`**

```python
from __future__ import annotations
import numpy as np
from loguru import logger
from voice_assistant.core.types import AudioSegment


def _load_silero():
    import torch
    model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
    return model


class VADSegmenter:
    def __init__(self, sample_rate: int, threshold: float,
                 min_speech_ms: int, max_speech_ms: int, model=None):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_ms = min_speech_ms
        self.max_ms = max_speech_ms
        self._model = model

    @property
    def model(self):
        if self._model is None:
            self._model = _load_silero()
        return self._model

    def _has_speech(self, samples: np.ndarray) -> bool:
        import torch
        f32 = samples.astype(np.float32) / 32768.0
        window = 512
        for i in range(0, len(f32) - window, window):
            chunk = torch.from_numpy(f32[i:i + window])
            if float(self.model(chunk, self.sample_rate).item()) >= self.threshold:
                return True
        return False

    def segment(self, samples: np.ndarray) -> AudioSegment | None:
        dur_ms = int(len(samples) * 1000 / self.sample_rate)
        if dur_ms < self.min_ms:
            logger.debug(f"segment {dur_ms}ms below min, discarded")
            return None
        if dur_ms > self.max_ms:
            logger.warning(f"segment {dur_ms}ms exceeds max, trimming")
            samples = samples[: int(self.max_ms * self.sample_rate / 1000)]
        if not self._has_speech(samples):
            logger.debug("no speech detected, discarded")
            return None
        return AudioSegment(samples=samples.astype(np.int16),
                            sample_rate=self.sample_rate)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/audio/test_vad.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/voice_assistant/audio/vad.py tests/unit/audio/test_vad.py
git commit -m "feat: silero VAD segmenter with length guards"
```

---

## Task 9: Activation interface + push-to-talk

**Files:**
- Create: `src/voice_assistant/activation/__init__.py`, `src/voice_assistant/activation/base.py`, `src/voice_assistant/activation/hotkey.py`
- Test: `tests/unit/activation/test_hotkey.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/activation/test_hotkey.py
from voice_assistant.activation.hotkey import PushToTalk


def test_press_then_release_emits_segment():
    captured = {}

    def on_capture(start_held: bool):
        captured["held"] = start_held

    ptt = PushToTalk(key_name="ctrl_r", on_state_change=on_capture)
    ptt._on_press_key()
    assert captured["held"] is True
    ptt._on_release_key()
    assert captured["held"] is False


def test_double_press_is_idempotent():
    states = []
    ptt = PushToTalk(key_name="ctrl_r", on_state_change=lambda h: states.append(h))
    ptt._on_press_key()
    ptt._on_press_key()
    assert states == [True]  # second press ignored while held
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/activation/test_hotkey.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/voice_assistant/activation/__init__.py`**

Empty file.

- [ ] **Step 4: Write `src/voice_assistant/activation/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod


class Activator(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
```

- [ ] **Step 5: Write `src/voice_assistant/activation/hotkey.py`**

```python
from __future__ import annotations
from typing import Callable
from loguru import logger
from voice_assistant.activation.base import Activator


class PushToTalk(Activator):
    def __init__(self, key_name: str, on_state_change: Callable[[bool], None]):
        self.key_name = key_name
        self._on_state_change = on_state_change
        self._held = False
        self._listener = None

    def _on_press_key(self) -> None:
        if self._held:
            return
        self._held = True
        self._on_state_change(True)

    def _on_release_key(self) -> None:
        if not self._held:
            return
        self._held = False
        self._on_state_change(False)

    def start(self) -> None:
        from pynput import keyboard

        target = getattr(keyboard.Key, self.key_name, None)
        if target is None:
            raise ValueError(f"Unknown hotkey: {self.key_name}")

        def on_press(key):
            if key == target:
                self._on_press_key()

        def on_release(key):
            if key == target:
                self._on_release_key()

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()
        logger.info(f"push-to-talk armed on {self.key_name}")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/activation/test_hotkey.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add src/voice_assistant/activation tests/unit/activation/test_hotkey.py
git commit -m "feat: push-to-talk activation"
```

---

## Task 10: ASR interface + faster-whisper engine

**Files:**
- Create: `src/voice_assistant/asr/__init__.py`, `src/voice_assistant/asr/base.py`, `src/voice_assistant/asr/faster_whisper_engine.py`
- Test: `tests/unit/asr/test_faster_whisper_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/asr/test_faster_whisper_engine.py
import numpy as np
from voice_assistant.asr.faster_whisper_engine import FasterWhisperEngine
from voice_assistant.core.types import AudioSegment


class FakeSeg:
    def __init__(self, text, logprob):
        self.text = text
        self.avg_logprob = logprob


class FakeModel:
    def transcribe(self, audio, language, beam_size):
        info = type("I", (), {"language": "ru", "language_probability": 0.95})()
        return [FakeSeg(" привет", -0.2), FakeSeg(" мир", -0.3)], info


def test_transcribe_joins_segments_and_maps_confidence():
    eng = FasterWhisperEngine(model="medium", device="cpu",
                              compute_type="int8", language="ru",
                              model_obj=FakeModel())
    seg = AudioSegment(samples=np.zeros(16000, dtype=np.int16), sample_rate=16000)
    t = eng.transcribe(seg)
    assert t.text == "привет мир"
    assert t.language == "ru"
    assert 0.0 <= t.confidence <= 1.0
    assert t.duration_ms == 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/asr/test_faster_whisper_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/voice_assistant/asr/__init__.py`**

Empty file.

- [ ] **Step 4: Write `src/voice_assistant/asr/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from voice_assistant.core.types import AudioSegment, Transcript


class ASREngine(ABC):
    @abstractmethod
    def transcribe(self, segment: AudioSegment) -> Transcript: ...
```

- [ ] **Step 5: Write `src/voice_assistant/asr/faster_whisper_engine.py`**

```python
from __future__ import annotations
import math
import numpy as np
from loguru import logger
from voice_assistant.asr.base import ASREngine
from voice_assistant.core.types import AudioSegment, Transcript


def _resolve_device(device: str) -> tuple[str, str]:
    if device == "auto":
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda", "int8_float16"
        except Exception:
            pass
        return "cpu", "int8"
    if device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning("CUDA requested but unavailable, falling back to CPU")
                return "cpu", "int8"
        except Exception:
            return "cpu", "int8"
    return device, ""


class FasterWhisperEngine(ASREngine):
    def __init__(self, model: str, device: str, compute_type: str,
                 language: str, model_obj=None):
        self.language = language
        if model_obj is not None:
            self._model = model_obj
        else:
            from faster_whisper import WhisperModel
            dev, fallback_ct = _resolve_device(device)
            ct = fallback_ct or compute_type
            logger.info(f"Loading whisper {model} on {dev} ({ct})")
            self._model = WhisperModel(model, device=dev, compute_type=ct)

    def transcribe(self, segment: AudioSegment) -> Transcript:
        audio = segment.samples.astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(
            audio, language=self.language, beam_size=5)
        seg_list = list(segments)
        text = " ".join(s.text.strip() for s in seg_list).strip()
        if seg_list:
            avg_lp = sum(s.avg_logprob for s in seg_list) / len(seg_list)
            confidence = max(0.0, min(1.0, math.exp(avg_lp)))
        else:
            confidence = 0.0
        return Transcript(
            text=text,
            language=getattr(info, "language", self.language),
            confidence=confidence,
            duration_ms=segment.duration_ms,
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/asr/test_faster_whisper_engine.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/voice_assistant/asr tests/unit/asr/test_faster_whisper_engine.py
git commit -m "feat: faster-whisper ASR engine with device fallback"
```

---

## Task 11: NLU interface + rules router + commands.yaml

**Files:**
- Create: `src/voice_assistant/nlu/__init__.py`, `src/voice_assistant/nlu/base.py`, `src/voice_assistant/nlu/rules.py`, `config/commands.yaml`
- Test: `tests/unit/nlu/test_rules.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/nlu/test_rules.py
import textwrap
import pytest
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.core.types import Transcript

COMMANDS = textwrap.dedent("""
- intent: open_app
  examples: ["открой {app}", "запусти {app}", "open {app}"]
  slots: {app: string}
- intent: volume_set
  examples: ["громкость {level:int}", "поставь громкость на {level:int}"]
  slots: {level: int}
- intent: minimize_all
  examples: ["сверни всё", "сверни все окна"]
  slots: {}
""")


@pytest.fixture
def router(tmp_path):
    f = tmp_path / "commands.yaml"
    f.write_text(COMMANDS, encoding="utf-8")
    return RulesRouter(commands_path=f, fuzzy_threshold=85)


def _t(text): return Transcript(text=text, language="ru", confidence=0.9, duration_ms=500)


def test_exact_slot_match(router):
    i = router.route(_t("открой телеграм"))
    assert i.name == "open_app"
    assert i.slots == {"app": "телеграм"}


def test_int_slot_coerced(router):
    i = router.route(_t("громкость 30"))
    assert i.name == "volume_set"
    assert i.slots == {"level": 30}


def test_no_slot_intent(router):
    i = router.route(_t("сверни всё"))
    assert i.name == "minimize_all"


def test_fuzzy_match_tolerates_typo(router):
    i = router.route(_t("свирни всё"))
    assert i.name == "minimize_all"


def test_garbage_returns_unknown(router):
    i = router.route(_t("абракадабра колбаса"))
    assert i.name == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/nlu/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/voice_assistant/nlu/__init__.py`**

Empty file.

- [ ] **Step 4: Write `src/voice_assistant/nlu/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from voice_assistant.core.types import Transcript, Intent


class NLURouter(ABC):
    @abstractmethod
    def route(self, transcript: Transcript) -> Intent: ...
```

- [ ] **Step 5: Write `src/voice_assistant/nlu/rules.py`**

```python
from __future__ import annotations
import re
from pathlib import Path
import yaml
from rapidfuzz import fuzz
from voice_assistant.nlu.base import NLURouter
from voice_assistant.core.types import Transcript, Intent

_SLOT_RE = re.compile(r"\{(\w+)(?::(\w+))?\}")


def _compile(example: str) -> tuple[re.Pattern, list[tuple[str, str]]]:
    slots: list[tuple[str, str]] = []
    pattern = "^"
    pos = 0
    for m in _SLOT_RE.finditer(example):
        pattern += re.escape(example[pos:m.start()])
        name, typ = m.group(1), m.group(2) or "string"
        slots.append((name, typ))
        pattern += r"(\d+)" if typ == "int" else r"(.+?)"
        pos = m.end()
    pattern += re.escape(example[pos:]) + "$"
    return re.compile(pattern, re.IGNORECASE), slots


class RulesRouter(NLURouter):
    def __init__(self, commands_path: str | Path, fuzzy_threshold: int = 85):
        raw = yaml.safe_load(Path(commands_path).read_text(encoding="utf-8")) or []
        self.fuzzy_threshold = fuzzy_threshold
        self._rules = []  # (intent, regex, slots, literal_template)
        for entry in raw:
            for ex in entry.get("examples", []):
                rx, slots = _compile(ex)
                literal = _SLOT_RE.sub("", ex).strip()
                self._rules.append((entry["intent"], rx, slots, literal))

    def _coerce(self, value: str, typ: str):
        return int(value) if typ == "int" else value.strip()

    def route(self, transcript: Transcript) -> Intent:
        text = transcript.text.strip().lower()
        if not text:
            return Intent.unknown()
        for intent, rx, slots, _ in self._rules:
            m = rx.match(text)
            if m:
                values = {n: self._coerce(g, t)
                          for (n, t), g in zip(slots, m.groups())}
                return Intent(name=intent, slots=values, confidence=1.0)
        # fuzzy on slotless rules
        best, best_score = None, 0
        for intent, _, slots, literal in self._rules:
            if slots or not literal:
                continue
            score = fuzz.ratio(text, literal.lower())
            if score > best_score:
                best, best_score = intent, score
        if best and best_score >= self.fuzzy_threshold:
            return Intent(name=best, slots={}, confidence=best_score / 100.0)
        return Intent.unknown()
```

- [ ] **Step 6: Create `config/commands.yaml`**

```yaml
- intent: open_app
  examples: ["открой {app}", "запусти {app}", "open {app}", "run {app}"]
  slots: {app: string}
- intent: close_app
  examples: ["закрой {app}", "закрой приложение {app}", "close {app}"]
  slots: {app: string}
- intent: minimize_all
  examples: ["сверни всё", "сверни все окна", "minimize all"]
  slots: {}
- intent: close_window
  examples: ["закрой текущее окно", "закрой окно", "close window"]
  slots: {}
- intent: switch_window
  examples: ["переключи окно", "следующее окно", "switch window"]
  slots: {}
- intent: web_search
  examples: ["найди в гугле {query}", "загугли {query}", "search {query}"]
  slots: {query: string}
- intent: open_url
  examples: ["открой сайт {url}", "перейди на {url}"]
  slots: {url: string}
- intent: open_bookmark
  examples: ["открой закладку {name}", "открой {name}"]
  slots: {name: string}
- intent: open_path
  examples: ["открой папку {name}", "открой директорию {name}"]
  slots: {name: string}
- intent: clipboard_copy
  examples: ["скопируй", "копировать", "copy"]
  slots: {}
- intent: clipboard_paste
  examples: ["вставь", "вставить", "paste"]
  slots: {}
- intent: clipboard_read
  examples: ["прочитай буфер", "что в буфере"]
  slots: {}
- intent: volume_set
  examples: ["громкость {level:int}", "поставь громкость на {level:int}"]
  slots: {level: int}
- intent: volume_up
  examples: ["сделай погромче", "громче", "volume up"]
  slots: {}
- intent: volume_down
  examples: ["сделай потише", "тише", "volume down"]
  slots: {}
- intent: lock_screen
  examples: ["заблокируй экран", "блокировка", "lock"]
  slots: {}
- intent: shutdown
  examples: ["выключи компьютер", "выключить компьютер"]
  slots: {}
- intent: reboot
  examples: ["перезагрузи компьютер", "перезагрузка"]
  slots: {}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/unit/nlu/test_rules.py -v`
Expected: PASS (5 tests)

- [ ] **Step 8: Commit**

```bash
git add src/voice_assistant/nlu config/commands.yaml tests/unit/nlu/test_rules.py
git commit -m "feat: rules-based NLU router with fuzzy fallback"
```

---

## Task 12: Executor registry

**Files:**
- Create: `src/voice_assistant/executor/__init__.py`, `src/voice_assistant/executor/registry.py`, `src/voice_assistant/executor/result.py`
- Test: `tests/unit/executor/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/executor/test_registry.py
import pytest
from voice_assistant.executor.registry import register_intent, Registry
from voice_assistant.core.types import Intent, ExecutionResult


def test_register_and_dispatch():
    reg = Registry()

    @register_intent("ping", registry=reg)
    def _ping(slots, ctx):
        return ExecutionResult.ok("pong")

    res = reg.dispatch(Intent(name="ping", slots={}), ctx=None)
    assert res.success and res.message == "pong"


def test_unknown_intent_returns_fail():
    reg = Registry()
    res = reg.dispatch(Intent.unknown(), ctx=None)
    assert res.success is False


def test_handler_exception_is_contained():
    reg = Registry()

    @register_intent("boom", registry=reg)
    def _boom(slots, ctx):
        raise RuntimeError("kaboom")

    res = reg.dispatch(Intent(name="boom", slots={}), ctx=None)
    assert res.success is False
    assert "kaboom" in res.message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/executor/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/voice_assistant/executor/__init__.py`**

Empty file.

- [ ] **Step 4: Write `src/voice_assistant/executor/result.py`**

```python
from voice_assistant.core.types import ExecutionResult

__all__ = ["ExecutionResult"]
```

- [ ] **Step 5: Write `src/voice_assistant/executor/registry.py`**

```python
from __future__ import annotations
from typing import Callable
from loguru import logger
from voice_assistant.core.types import Intent, ExecutionResult

Handler = Callable[[dict, object], ExecutionResult]


class Registry:
    def __init__(self):
        self._handlers: dict[str, Handler] = {}

    def add(self, name: str, fn: Handler) -> None:
        self._handlers[name] = fn

    def dispatch(self, intent: Intent, ctx: object) -> ExecutionResult:
        fn = self._handlers.get(intent.name)
        if fn is None:
            return ExecutionResult.fail(
                f"unknown intent: {intent.name}",
                tts_response="Не понял, повтори")
        try:
            return fn(intent.slots, ctx)
        except Exception as e:  # contained: pipeline must survive
            logger.exception(f"plugin {intent.name} failed")
            return ExecutionResult.fail(f"plugin error: {e}",
                                        tts_response="Ошибка выполнения")


_GLOBAL = Registry()


def register_intent(name: str, registry: Registry | None = None):
    target = registry or _GLOBAL

    def deco(fn: Handler) -> Handler:
        target.add(name, fn)
        return fn

    return deco


def global_registry() -> Registry:
    return _GLOBAL
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/executor/test_registry.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add src/voice_assistant/executor/__init__.py src/voice_assistant/executor/registry.py src/voice_assistant/executor/result.py tests/unit/executor/test_registry.py
git commit -m "feat: executor registry with contained plugin errors"
```

---

## Task 13: ExecutorContext

**Files:**
- Create: `src/voice_assistant/executor/context.py`
- Test: `tests/unit/executor/test_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/executor/test_context.py
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig


def test_context_exposes_config_and_platform():
    ctx = ExecutorContext(config=AppConfig(), platform_ops=object())
    assert ctx.config is not None
    assert ctx.platform_ops is not None


def test_resolve_app_alias():
    cfg = AppConfig(app_aliases={"телега": "telegram"})
    ctx = ExecutorContext(config=cfg, platform_ops=object())
    assert ctx.resolve_app("телега") == "telegram"
    assert ctx.resolve_app("notepad") == "notepad"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/executor/test_context.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/executor/context.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from voice_assistant.config import AppConfig


@dataclass
class ExecutorContext:
    config: AppConfig
    platform_ops: object

    def resolve_app(self, name: str) -> str:
        return self.config.app_aliases.get(name.strip().lower(), name.strip())

    def resolve_path(self, name: str) -> str:
        return self.config.path_aliases.get(name.strip().lower(), name.strip())

    def resolve_bookmark(self, name: str) -> str | None:
        return self.config.bookmarks.get(name.strip().lower())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/executor/test_context.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/voice_assistant/executor/context.py tests/unit/executor/test_context.py
git commit -m "feat: executor context with alias resolution"
```

---

## Task 14: Plugin — apps

**Files:**
- Create: `src/voice_assistant/executor/plugins/__init__.py`, `src/voice_assistant/executor/plugins/apps.py`
- Test: `tests/unit/executor/plugins/test_apps.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/executor/plugins/test_apps.py
from unittest.mock import MagicMock
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.apps as apps


def _ctx():
    return ExecutorContext(config=AppConfig(app_aliases={"телега": "telegram"}),
                           platform_ops=MagicMock())


def test_open_app_resolves_alias_and_launches():
    reg = Registry()
    apps.register(reg)
    ctx = _ctx()
    res = reg.dispatch(Intent("open_app", {"app": "телега"}), ctx)
    ctx.platform_ops.launch_app.assert_called_once_with("telegram")
    assert res.success


def test_close_app_calls_platform():
    reg = Registry()
    apps.register(reg)
    ctx = _ctx()
    res = reg.dispatch(Intent("close_app", {"app": "telegram"}), ctx)
    ctx.platform_ops.close_app.assert_called_once_with("telegram")
    assert res.success
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/executor/plugins/test_apps.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/voice_assistant/executor/plugins/__init__.py`**

```python
from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import (
    apps, windows, browser, files, clipboard, system,
)


def register_all() -> None:
    reg = global_registry()
    for mod in (apps, windows, browser, files, clipboard, system):
        mod.register(reg)
```

> NOTE: this file imports modules created in Tasks 14-19. Until all exist,
> create it with only the modules that exist so far, or create stub modules.
> Final form (all six) is shown above; adjust the import tuple per task.

- [ ] **Step 4: Write `src/voice_assistant/executor/plugins/apps.py`**

```python
from __future__ import annotations
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def register(reg: Registry) -> None:
    def open_app(slots, ctx) -> ExecutionResult:
        target = ctx.resolve_app(slots.get("app", ""))
        if not target:
            return ExecutionResult.fail("no app given", "Какое приложение?")
        ctx.platform_ops.launch_app(target)
        return ExecutionResult.ok(f"launched {target}", f"Открыл {target}")

    def close_app(slots, ctx) -> ExecutionResult:
        target = ctx.resolve_app(slots.get("app", ""))
        if not target:
            return ExecutionResult.fail("no app given", "Какое приложение?")
        ctx.platform_ops.close_app(target)
        return ExecutionResult.ok(f"closed {target}", f"Закрыл {target}")

    reg.add("open_app", open_app)
    reg.add("close_app", close_app)
```

- [ ] **Step 5: Create temporary `plugins/__init__.py` with apps only**

```python
from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import apps


def register_all() -> None:
    reg = global_registry()
    apps.register(reg)
```

(This is replaced in Task 19 with the full version.)

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/executor/plugins/test_apps.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add src/voice_assistant/executor/plugins/__init__.py src/voice_assistant/executor/plugins/apps.py tests/unit/executor/plugins/test_apps.py
git commit -m "feat: apps plugin (open/close)"
```

---

## Task 15: Plugin — windows

**Files:**
- Create: `src/voice_assistant/executor/plugins/windows.py`
- Modify: `src/voice_assistant/executor/plugins/__init__.py` (add `windows`)
- Test: `tests/unit/executor/plugins/test_windows.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/executor/plugins/test_windows.py
from unittest.mock import MagicMock, patch
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.windows as win


def _ctx():
    return ExecutorContext(config=AppConfig(), platform_ops=MagicMock())


def test_minimize_all_sends_win_d():
    reg = Registry()
    win.register(reg)
    with patch.object(win, "_press") as press:
        res = reg.dispatch(Intent("minimize_all", {}), _ctx())
    press.assert_called_once_with("win", "d")
    assert res.success


def test_close_window_sends_alt_f4():
    reg = Registry()
    win.register(reg)
    with patch.object(win, "_press") as press:
        res = reg.dispatch(Intent("close_window", {}), _ctx())
    press.assert_called_once_with("alt", "f4")
    assert res.success


def test_switch_window_sends_alt_tab():
    reg = Registry()
    win.register(reg)
    with patch.object(win, "_press") as press:
        res = reg.dispatch(Intent("switch_window", {}), _ctx())
    press.assert_called_once_with("alt", "tab")
    assert res.success
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/executor/plugins/test_windows.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/executor/plugins/windows.py`**

```python
from __future__ import annotations
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def _press(*keys: str) -> None:
    import pyautogui
    pyautogui.hotkey(*keys)


def register(reg: Registry) -> None:
    def minimize_all(slots, ctx) -> ExecutionResult:
        _press("win", "d")
        return ExecutionResult.ok("minimized all", "Свернул всё")

    def close_window(slots, ctx) -> ExecutionResult:
        _press("alt", "f4")
        return ExecutionResult.ok("closed window", "Закрыл окно")

    def switch_window(slots, ctx) -> ExecutionResult:
        _press("alt", "tab")
        return ExecutionResult.ok("switched window", "Переключил")

    reg.add("minimize_all", minimize_all)
    reg.add("close_window", close_window)
    reg.add("switch_window", switch_window)
```

- [ ] **Step 4: Add `pyautogui` to deps**

Modify `pyproject.toml`: add `"pyautogui"` to dependencies. Run `pip install -e ".[dev]"`.

- [ ] **Step 5: Update `plugins/__init__.py`**

```python
from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import apps, windows


def register_all() -> None:
    reg = global_registry()
    apps.register(reg)
    windows.register(reg)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/executor/plugins/test_windows.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add src/voice_assistant/executor/plugins/windows.py src/voice_assistant/executor/plugins/__init__.py pyproject.toml tests/unit/executor/plugins/test_windows.py
git commit -m "feat: windows plugin (minimize/close/switch)"
```

---

## Task 16: Plugin — browser

**Files:**
- Create: `src/voice_assistant/executor/plugins/browser.py`
- Modify: `src/voice_assistant/executor/plugins/__init__.py` (add `browser`)
- Test: `tests/unit/executor/plugins/test_browser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/executor/plugins/test_browser.py
from unittest.mock import MagicMock, patch
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.browser as br


def _ctx(bookmarks=None):
    return ExecutorContext(config=AppConfig(bookmarks=bookmarks or {}),
                           platform_ops=MagicMock())


def test_web_search_opens_google_query():
    reg = Registry()
    br.register(reg)
    with patch.object(br.webbrowser, "open") as op:
        res = reg.dispatch(Intent("web_search", {"query": "погода завтра"}), _ctx())
    url = op.call_args[0][0]
    assert "google.com/search" in url and "%D0" in url  # url-encoded cyrillic
    assert res.success


def test_open_url_normalizes_scheme():
    reg = Registry()
    br.register(reg)
    with patch.object(br.webbrowser, "open") as op:
        reg.dispatch(Intent("open_url", {"url": "example.com"}), _ctx())
    assert op.call_args[0][0] == "https://example.com"


def test_open_bookmark_uses_config():
    reg = Registry()
    br.register(reg)
    ctx = _ctx(bookmarks={"ютуб": "https://youtube.com"})
    with patch.object(br.webbrowser, "open") as op:
        res = reg.dispatch(Intent("open_bookmark", {"name": "ютуб"}), ctx)
    assert op.call_args[0][0] == "https://youtube.com"
    assert res.success


def test_unknown_bookmark_fails():
    reg = Registry()
    br.register(reg)
    res = reg.dispatch(Intent("open_bookmark", {"name": "несуществует"}), _ctx())
    assert res.success is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/executor/plugins/test_browser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/executor/plugins/browser.py`**

```python
from __future__ import annotations
import webbrowser
from urllib.parse import quote_plus
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def register(reg: Registry) -> None:
    def web_search(slots, ctx) -> ExecutionResult:
        q = slots.get("query", "").strip()
        if not q:
            return ExecutionResult.fail("empty query", "Что искать?")
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(q)}")
        return ExecutionResult.ok(f"searched {q}", f"Ищу {q}")

    def open_url(slots, ctx) -> ExecutionResult:
        url = slots.get("url", "").strip()
        if not url:
            return ExecutionResult.fail("empty url", "Какой адрес?")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return ExecutionResult.ok(f"opened {url}", "Открываю")

    def open_bookmark(slots, ctx) -> ExecutionResult:
        url = ctx.resolve_bookmark(slots.get("name", ""))
        if not url:
            return ExecutionResult.fail("unknown bookmark", "Нет такой закладки")
        webbrowser.open(url)
        return ExecutionResult.ok(f"opened {url}", "Открываю")

    reg.add("web_search", web_search)
    reg.add("open_url", open_url)
    reg.add("open_bookmark", open_bookmark)
```

- [ ] **Step 4: Update `plugins/__init__.py`**

```python
from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import apps, windows, browser


def register_all() -> None:
    reg = global_registry()
    apps.register(reg)
    windows.register(reg)
    browser.register(reg)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/executor/plugins/test_browser.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/executor/plugins/browser.py src/voice_assistant/executor/plugins/__init__.py tests/unit/executor/plugins/test_browser.py
git commit -m "feat: browser plugin (search/url/bookmark)"
```

---

## Task 17: Plugin — files

**Files:**
- Create: `src/voice_assistant/executor/plugins/files.py`
- Modify: `src/voice_assistant/executor/plugins/__init__.py` (add `files`)
- Test: `tests/unit/executor/plugins/test_files.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/executor/plugins/test_files.py
from unittest.mock import MagicMock
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.files as files


def test_open_path_resolves_alias_and_calls_platform():
    reg = Registry()
    files.register(reg)
    cfg = AppConfig(path_aliases={"загрузки": "~/Downloads"})
    ctx = ExecutorContext(config=cfg, platform_ops=MagicMock())
    res = reg.dispatch(Intent("open_path", {"name": "загрузки"}), ctx)
    ctx.platform_ops.open_path.assert_called_once_with("~/Downloads")
    assert res.success


def test_open_path_empty_fails():
    reg = Registry()
    files.register(reg)
    ctx = ExecutorContext(config=AppConfig(), platform_ops=MagicMock())
    res = reg.dispatch(Intent("open_path", {"name": ""}), ctx)
    assert res.success is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/executor/plugins/test_files.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/executor/plugins/files.py`**

```python
from __future__ import annotations
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def register(reg: Registry) -> None:
    def open_path(slots, ctx) -> ExecutionResult:
        name = slots.get("name", "").strip()
        if not name:
            return ExecutionResult.fail("no path", "Что открыть?")
        target = ctx.resolve_path(name)
        ctx.platform_ops.open_path(target)
        return ExecutionResult.ok(f"opened {target}", f"Открыл {name}")

    reg.add("open_path", open_path)
```

- [ ] **Step 4: Update `plugins/__init__.py`**

```python
from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import apps, windows, browser, files


def register_all() -> None:
    reg = global_registry()
    apps.register(reg)
    windows.register(reg)
    browser.register(reg)
    files.register(reg)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/executor/plugins/test_files.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/executor/plugins/files.py src/voice_assistant/executor/plugins/__init__.py tests/unit/executor/plugins/test_files.py
git commit -m "feat: files plugin (open path by alias)"
```

---

## Task 18: Plugin — clipboard

**Files:**
- Create: `src/voice_assistant/executor/plugins/clipboard.py`
- Modify: `src/voice_assistant/executor/plugins/__init__.py` (add `clipboard`)
- Test: `tests/unit/executor/plugins/test_clipboard.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/executor/plugins/test_clipboard.py
from unittest.mock import MagicMock, patch
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.clipboard as cb


def _ctx():
    return ExecutorContext(config=AppConfig(), platform_ops=MagicMock())


def test_copy_sends_ctrl_c():
    reg = Registry()
    cb.register(reg)
    with patch.object(cb, "_press") as press:
        res = reg.dispatch(Intent("clipboard_copy", {}), _ctx())
    press.assert_called_once_with("ctrl", "c")
    assert res.success


def test_paste_sends_ctrl_v():
    reg = Registry()
    cb.register(reg)
    with patch.object(cb, "_press") as press:
        res = reg.dispatch(Intent("clipboard_paste", {}), _ctx())
    press.assert_called_once_with("ctrl", "v")
    assert res.success


def test_read_returns_clipboard_text():
    reg = Registry()
    cb.register(reg)
    with patch.object(cb, "_read_clipboard", return_value="привет"):
        res = reg.dispatch(Intent("clipboard_read", {}), _ctx())
    assert "привет" in res.tts_response
    assert res.success
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/executor/plugins/test_clipboard.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/executor/plugins/clipboard.py`**

```python
from __future__ import annotations
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def _press(*keys: str) -> None:
    import pyautogui
    pyautogui.hotkey(*keys)


def _read_clipboard() -> str:
    import ctypes
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard(0)
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        text = ctypes.c_wchar_p(ptr).value or ""
        kernel32.GlobalUnlock(handle)
        return text
    finally:
        user32.CloseClipboard()


def register(reg: Registry) -> None:
    def copy(slots, ctx) -> ExecutionResult:
        _press("ctrl", "c")
        return ExecutionResult.ok("copied", "Скопировал")

    def paste(slots, ctx) -> ExecutionResult:
        _press("ctrl", "v")
        return ExecutionResult.ok("pasted", "Вставил")

    def read(slots, ctx) -> ExecutionResult:
        text = _read_clipboard()
        if not text:
            return ExecutionResult.ok("clipboard empty", "Буфер пуст")
        snippet = text[:200]
        return ExecutionResult.ok(f"clipboard: {snippet}",
                                  f"В буфере: {snippet}")

    reg.add("clipboard_copy", copy)
    reg.add("clipboard_paste", paste)
    reg.add("clipboard_read", read)
```

- [ ] **Step 4: Update `plugins/__init__.py`**

```python
from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import apps, windows, browser, files, clipboard


def register_all() -> None:
    reg = global_registry()
    apps.register(reg)
    windows.register(reg)
    browser.register(reg)
    files.register(reg)
    clipboard.register(reg)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/executor/plugins/test_clipboard.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/voice_assistant/executor/plugins/clipboard.py src/voice_assistant/executor/plugins/__init__.py tests/unit/executor/plugins/test_clipboard.py
git commit -m "feat: clipboard plugin (copy/paste/read)"
```

---

## Task 19: Plugin — system (with confirmation)

**Files:**
- Create: `src/voice_assistant/executor/plugins/system.py`
- Modify: `src/voice_assistant/executor/plugins/__init__.py` (final form: all six)
- Test: `tests/unit/executor/plugins/test_system.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/executor/plugins/test_system.py
from unittest.mock import MagicMock
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import ExecutionResult, Intent
import voice_assistant.executor.plugins.system as sysmod


def _ctx(ops=None):
    return ExecutorContext(config=AppConfig(), platform_ops=ops or MagicMock())


def test_volume_set_calls_platform():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    reg.dispatch(Intent("volume_set", {"level": 40}), _ctx(ops))
    ops.set_volume.assert_called_once_with(40)


def test_lock_calls_platform():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    res = reg.dispatch(Intent("lock_screen", {}), _ctx(ops))
    ops.lock_screen.assert_called_once()
    assert res.success


def test_shutdown_requires_confirmation_not_executed_immediately():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    res = reg.dispatch(Intent("shutdown", {}), _ctx(ops))
    ops.shutdown.assert_not_called()
    assert res.success is True
    assert "подтверд" in res.tts_response.lower()


def test_confirm_yes_executes_pending_shutdown():
    reg = Registry()
    sysmod.register(reg)
    ops = MagicMock()
    ctx = _ctx(ops)
    reg.dispatch(Intent("shutdown", {}), ctx)
    res = reg.dispatch(Intent("confirm_yes", {}), ctx)
    ops.shutdown.assert_called_once_with(reboot=False)
    assert res.success
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/executor/plugins/test_system.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/executor/plugins/system.py`**

```python
from __future__ import annotations
import time
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult

CONFIRM_TIMEOUT_S = 5.0


def register(reg: Registry) -> None:
    pending = {"action": None, "ts": 0.0}

    def _arm(action: str) -> ExecutionResult:
        pending["action"] = action
        pending["ts"] = time.monotonic()
        return ExecutionResult.ok(
            f"awaiting confirm for {action}",
            "Подтвердите: скажите «да»")

    def volume_set(slots, ctx) -> ExecutionResult:
        level = int(slots.get("level", 50))
        ctx.platform_ops.set_volume(level)
        return ExecutionResult.ok(f"volume {level}", f"Громкость {level}")

    def volume_up(slots, ctx) -> ExecutionResult:
        ctx.platform_ops.set_volume(_clamp(_current(ctx) + 5))
        return ExecutionResult.ok("volume up", "Громче")

    def volume_down(slots, ctx) -> ExecutionResult:
        ctx.platform_ops.set_volume(_clamp(_current(ctx) - 5))
        return ExecutionResult.ok("volume down", "Тише")

    def _current(ctx) -> int:
        getter = getattr(ctx.platform_ops, "get_volume", None)
        return getter() if callable(getter) else 50

    def _clamp(v: int) -> int:
        return max(0, min(100, v))

    def lock_screen(slots, ctx) -> ExecutionResult:
        ctx.platform_ops.lock_screen()
        return ExecutionResult.ok("locked", "Заблокировал")

    def shutdown(slots, ctx) -> ExecutionResult:
        return _arm("shutdown")

    def reboot(slots, ctx) -> ExecutionResult:
        return _arm("reboot")

    def confirm_yes(slots, ctx) -> ExecutionResult:
        action = pending["action"]
        if not action:
            return ExecutionResult.ok("nothing to confirm", "Нечего подтверждать")
        if time.monotonic() - pending["ts"] > CONFIRM_TIMEOUT_S:
            pending["action"] = None
            return ExecutionResult.ok("confirm expired", "Время вышло, отмена")
        pending["action"] = None
        ctx.platform_ops.shutdown(reboot=(action == "reboot"))
        return ExecutionResult.ok(f"executing {action}", "Выполняю")

    reg.add("volume_set", volume_set)
    reg.add("volume_up", volume_up)
    reg.add("volume_down", volume_down)
    reg.add("lock_screen", lock_screen)
    reg.add("shutdown", shutdown)
    reg.add("reboot", reboot)
    reg.add("confirm_yes", confirm_yes)
```

- [ ] **Step 4: Add `confirm_yes` to `config/commands.yaml`**

Append:

```yaml
- intent: confirm_yes
  examples: ["да", "подтверждаю", "yes"]
  slots: {}
```

- [ ] **Step 5: Replace `plugins/__init__.py` with final form**

```python
from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.plugins import (
    apps, windows, browser, files, clipboard, system,
)


def register_all() -> None:
    reg = global_registry()
    for mod in (apps, windows, browser, files, clipboard, system):
        mod.register(reg)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/executor/plugins/test_system.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Run full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/voice_assistant/executor/plugins/system.py src/voice_assistant/executor/plugins/__init__.py config/commands.yaml tests/unit/executor/plugins/test_system.py
git commit -m "feat: system plugin with voice confirmation flow"
```

---

## Task 20: Pipeline assembly + graceful shutdown

**Files:**
- Create: `src/voice_assistant/main.py`
- Test: `tests/unit/test_main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_main.py
from unittest.mock import MagicMock
from voice_assistant.main import Pipeline
from voice_assistant.config import AppConfig
from voice_assistant.core.types import AudioSegment, Transcript, Intent
import numpy as np


def test_pipeline_processes_one_segment_end_to_end():
    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой telegram", "ru", 0.9, 500)
    nlu = MagicMock()
    nlu.route.return_value = Intent("open_app", {"app": "telegram"}, 1.0)
    registry = MagicMock()
    registry.dispatch.return_value = type("R", (), {
        "success": True, "message": "ok", "tts_response": "Открыл"})()
    feedback = MagicMock()

    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    seg = AudioSegment(np.zeros(8000, dtype=np.int16), 16000)
    pipe.process_segment(seg)

    asr.transcribe.assert_called_once()
    nlu.route.assert_called_once()
    registry.dispatch.assert_called_once()
    feedback.emit.assert_called_once()


def test_low_confidence_transcript_skips_dispatch():
    cfg = AppConfig()
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("...", "ru", 0.1, 200)
    nlu = MagicMock()
    registry = MagicMock()
    feedback = MagicMock()
    pipe = Pipeline(config=cfg, asr=asr, nlu=nlu, registry=registry,
                    ctx=object(), feedback=feedback)
    pipe.process_segment(AudioSegment(np.zeros(3200, dtype=np.int16), 16000))
    registry.dispatch.assert_not_called()
    feedback.emit.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `src/voice_assistant/main.py`**

```python
from __future__ import annotations
import queue
import signal
import threading
from pathlib import Path
from loguru import logger

from voice_assistant.config import load_config, AppConfig
from voice_assistant.core.queues import PipelineQueues, STOP
from voice_assistant.core.types import AudioSegment
from voice_assistant.utils.logging import setup_logging
from voice_assistant.utils.platform import get_platform_ops
from voice_assistant.audio.capture import AudioCapture
from voice_assistant.audio.vad import VADSegmenter
from voice_assistant.activation.hotkey import PushToTalk
from voice_assistant.asr.faster_whisper_engine import FasterWhisperEngine
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.executor.registry import global_registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.executor.plugins import register_all
from voice_assistant.feedback.cli import CLIFeedback


class Pipeline:
    def __init__(self, config: AppConfig, asr, nlu, registry, ctx, feedback):
        self.config = config
        self.asr = asr
        self.nlu = nlu
        self.registry = registry
        self.ctx = ctx
        self.feedback = feedback

    def process_segment(self, segment: AudioSegment) -> None:
        transcript = self.asr.transcribe(segment)
        logger.info(f"ASR: '{transcript.text}' "
                    f"(conf={transcript.confidence:.2f})")
        if transcript.confidence < self.config.asr.min_confidence \
                or not transcript.text.strip():
            self.feedback.emit("Не понял, повтори", success=False)
            return
        intent = self.nlu.route(transcript)
        if intent.name == "unknown":
            self.feedback.emit("Не понял, повтори", success=False)
            return
        result = self.registry.dispatch(intent, self.ctx)
        self.feedback.emit(result.tts_response, success=result.success)


def _build(config_path: str) -> tuple[Pipeline, PipelineQueues,
                                       AudioCapture, PushToTalk, VADSegmenter]:
    cfg = load_config(config_path)
    setup_logging(level=cfg.log_level)
    register_all()
    ops = get_platform_ops()
    ctx = ExecutorContext(config=cfg, platform_ops=ops)
    asr = FasterWhisperEngine(
        model=cfg.asr.model, device=cfg.asr.device,
        compute_type=cfg.asr.compute_type, language=cfg.asr.language)
    nlu = RulesRouter(
        commands_path=str(Path(config_path).parent / "commands.yaml"),
        fuzzy_threshold=cfg.nlu.fuzzy_threshold)
    feedback = CLIFeedback()
    pipe = Pipeline(cfg, asr, nlu, global_registry(), ctx, feedback)

    qs = PipelineQueues()
    capture = AudioCapture(cfg.audio.sample_rate, cfg.audio.ring_seconds,
                           cfg.audio.input_device)
    vad = VADSegmenter(cfg.audio.sample_rate, cfg.vad.threshold,
                       cfg.vad.min_speech_ms, cfg.vad.max_speech_ms)

    def on_state_change(held: bool) -> None:
        if held:
            capture.ring._mark = len(capture.ring.snapshot())
        else:
            raw = capture.ring.snapshot()
            qs.speech_q.put(raw)

    ptt = PushToTalk(cfg.hotkey.push_to_talk, on_state_change)
    return pipe, qs, capture, ptt, vad


def _worker(pipe: Pipeline, qs: PipelineQueues, vad: VADSegmenter,
            stop_evt: threading.Event) -> None:
    while not stop_evt.is_set():
        try:
            raw = qs.speech_q.get(timeout=0.5)
        except queue.Empty:
            continue
        if raw is STOP:
            break
        segment = vad.segment(raw)
        if segment is None:
            pipe.feedback.emit("Не расслышал", success=False)
            continue
        pipe.process_segment(segment)


def main() -> int:
    config_path = "config/default.yaml"
    pipe, qs, capture, ptt, vad = _build(config_path)
    stop_evt = threading.Event()

    def _shutdown(*_):
        logger.info("shutting down")
        stop_evt.set()
        qs.speech_q.put(STOP)

    signal.signal(signal.SIGINT, _shutdown)
    try:
        capture.start()
    except Exception:
        logger.error("microphone unavailable, exiting")
        return 1
    ptt.start()
    worker = threading.Thread(target=_worker, args=(pipe, qs, vad, stop_evt),
                              daemon=True)
    worker.start()
    logger.info("ready — hold push-to-talk key and speak")
    worker.join()
    ptt.stop()
    capture.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/voice_assistant/main.py tests/unit/test_main.py
git commit -m "feat: pipeline assembly with graceful shutdown"
```

---

## Task 21: CLI feedback sink

**Files:**
- Create: `src/voice_assistant/feedback/__init__.py`, `src/voice_assistant/feedback/base.py`, `src/voice_assistant/feedback/cli.py`
- Test: `tests/unit/feedback/test_cli.py`

> NOTE: `main.py` imports `CLIFeedback` — this task must be completed before
> running `main.py`, but its unit can be built/tested independently. If doing
> tasks in order, move this before Task 20 or accept that `test_main.py` mocks
> feedback so it passes without this module; `main()` runtime needs it.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/feedback/test_cli.py
from unittest.mock import patch
from voice_assistant.feedback.cli import CLIFeedback


def test_emit_prints_and_notifies(capsys):
    fb = CLIFeedback()
    with patch.object(fb, "_notify") as notify:
        fb.emit("Открыл telegram", success=True)
    out = capsys.readouterr().out
    assert "Открыл telegram" in out
    notify.assert_called_once()


def test_emit_failure_marked(capsys):
    fb = CLIFeedback()
    with patch.object(fb, "_notify"):
        fb.emit("Не понял", success=False)
    assert "Не понял" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/feedback/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `src/voice_assistant/feedback/__init__.py`**

Empty file.

- [ ] **Step 4: Write `src/voice_assistant/feedback/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod


class FeedbackSink(ABC):
    @abstractmethod
    def emit(self, message: str, success: bool = True) -> None: ...
```

- [ ] **Step 5: Write `src/voice_assistant/feedback/cli.py`**

```python
from __future__ import annotations
from loguru import logger
from voice_assistant.feedback.base import FeedbackSink


class CLIFeedback(FeedbackSink):
    def _notify(self, message: str) -> None:
        try:
            from plyer import notification
            notification.notify(title="Voice Assistant",
                                 message=message, timeout=3)
        except Exception as e:
            logger.debug(f"notification failed: {e}")

    def emit(self, message: str, success: bool = True) -> None:
        prefix = "[OK]" if success else "[!!]"
        print(f"{prefix} {message}", flush=True)
        logger.info(f"feedback: {message} (success={success})")
        self._notify(message)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/unit/feedback/test_cli.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add src/voice_assistant/feedback tests/unit/feedback/test_cli.py
git commit -m "feat: CLI feedback sink with desktop notifications"
```

---

## Task 22: Integration test through pipeline

**Files:**
- Create: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Write the integration test (uses fakes, no hardware)**

```python
# tests/integration/test_pipeline.py
import numpy as np
from unittest.mock import MagicMock
from voice_assistant.config import AppConfig
from voice_assistant.nlu.rules import RulesRouter
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.core.types import AudioSegment, Transcript
from voice_assistant.main import Pipeline
import voice_assistant.executor.plugins.apps as apps


def test_open_app_flows_from_transcript_to_plugin(tmp_path):
    cmds = tmp_path / "commands.yaml"
    cmds.write_text(
        '- intent: open_app\n'
        '  examples: ["открой {app}"]\n'
        '  slots: {app: string}\n', encoding="utf-8")

    cfg = AppConfig(app_aliases={"телега": "telegram"})
    asr = MagicMock()
    asr.transcribe.return_value = Transcript("открой телега", "ru", 0.9, 500)
    nlu = RulesRouter(commands_path=cmds, fuzzy_threshold=85)
    reg = Registry()
    apps.register(reg)
    ops = MagicMock()
    ctx = ExecutorContext(config=cfg, platform_ops=ops)
    feedback = MagicMock()

    pipe = Pipeline(cfg, asr, nlu, reg, ctx, feedback)
    pipe.process_segment(AudioSegment(np.zeros(8000, dtype=np.int16), 16000))

    ops.launch_app.assert_called_once_with("telegram")
    feedback.emit.assert_called_once()
    assert feedback.emit.call_args.kwargs.get("success", True) is True
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/integration/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 3: Run full suite with coverage**

Run: `pytest --cov=voice_assistant --cov-report=term-missing -q`
Expected: all pass; coverage ≥ 80% on logic modules (hardware wrappers
`capture.py` stream callback and silero loader are excluded by being mocked).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_pipeline.py
git commit -m "test: end-to-end pipeline integration test"
```

---

## Task 23: ASR benchmark script

**Files:**
- Create: `scripts/benchmark_asr.py`

- [ ] **Step 1: Write `scripts/benchmark_asr.py`**

```python
"""Measure ASR latency and rough WER across models.

Usage: python scripts/benchmark_asr.py path/to/audio.wav "reference text"
"""
from __future__ import annotations
import sys
import time
import wave
import numpy as np
from voice_assistant.asr.faster_whisper_engine import FasterWhisperEngine
from voice_assistant.core.types import AudioSegment


def _load_wav(path: str) -> AudioSegment:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        frames = w.readframes(w.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16)
    return AudioSegment(samples=samples, sample_rate=sr)


def _wer(ref: str, hyp: str) -> float:
    r, h = ref.split(), hyp.split()
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + cost)
    return d[len(r)][len(h)] / max(1, len(r))


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    wav, ref = sys.argv[1], sys.argv[2]
    seg = _load_wav(wav)
    for model in ("small", "medium"):
        eng = FasterWhisperEngine(model=model, device="cuda",
                                  compute_type="int8_float16", language="ru")
        t0 = time.perf_counter()
        tr = eng.transcribe(seg)
        dt = time.perf_counter() - t0
        print(f"{model}: latency={dt:.2f}s wer={_wer(ref, tr.text):.2%} "
              f"text='{tr.text}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-check it imports**

Run: `python -c "import ast; ast.parse(open('scripts/benchmark_asr.py', encoding='utf-8').read())"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/benchmark_asr.py
git commit -m "feat: ASR latency/WER benchmark script"
```

---

## Task 24: Manual verification checklist + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Voice PC Assistant — MVP

Push-to-talk voice assistant: hold `Right Ctrl`, speak a command, release.

## Setup
```
pip install -e ".[dev]"
python -m voice_assistant.main
```
Config: `config/default.yaml`, commands: `config/commands.yaml`.

## Manual verification checklist (run before tagging MVP)
- [ ] Hold Right Ctrl, say "открой блокнот" → notepad launches
- [ ] "сверни всё" → desktop shows
- [ ] "закрой текущее окно" → active window closes
- [ ] "найди в гугле погода" → browser opens Google results
- [ ] "открой папку загрузки" → Downloads opens
- [ ] "скопируй" then "вставь" → clipboard works
- [ ] "громкость 20" → system volume changes
- [ ] "заблокируй экран" → screen locks
- [ ] "выключи компьютер" → asks confirmation; "да" within 5s proceeds (cancel by waiting out timeout during test)
- [ ] Garbage speech → "Не понял, повтори", no action
- [ ] Ctrl+C → clean shutdown, no traceback
- [ ] Latency end-of-speech → action start ≤ 1.5s (use benchmark_asr.py)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: MVP README and manual verification checklist"
```

---

## Self-Review Notes

- **Spec coverage:** capture+ring (T7), VAD with guards (T8), push-to-talk (T9), faster-whisper + CUDA fallback (T10), rules NLU + fuzzy (T11), registry + contained errors (T12), context/aliases (T13), all 6 plugins incl. confirmation (T14-19), pipeline + graceful shutdown (T20), feedback (T21), integration (T22), benchmark/latency (T23), manual checklist (T24), config/pydantic (T3), logging+privacy flag (T4), platform abstraction (T5). All spec sections mapped.
- **Task ordering caveat:** Task 21 (CLIFeedback) is imported by Task 20's `main.py` runtime path. `test_main.py` mocks feedback so Task 20 tests pass standalone; if executing strictly in order, Task 21 must be done before running `main()` for real (noted in Task 21). Recommended execution order: do Task 21 immediately after Task 20.
- **Type consistency:** DTOs (`AudioSegment`, `Transcript`, `Intent`, `ExecutionResult`) and signatures (`ASREngine.transcribe`, `NLURouter.route`, `Registry.dispatch(intent, ctx)`, plugin `register(reg)`, handler `(slots, ctx)`) consistent across all tasks.
- **Out of MVP scope (deferred to Beta/Release sub-projects):** wake word, Piper TTS, tray, dictation, ollama LLM fallback, Linux/macOS adapters, installer, dialog context.
