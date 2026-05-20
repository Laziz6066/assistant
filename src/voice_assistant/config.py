from __future__ import annotations
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ValidationError, Field, field_validator


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


class TTSConfig(BaseModel):
    enabled: bool = True
    voice: str = "ru_RU-irina-medium"
    voices_dir: Path = Field(
        default_factory=lambda: Path.home() / ".voice-assistant" / "voices"
    )
    length_scale: float = 1.0

    @field_validator("voices_dir", mode="before")
    @classmethod
    def _expand_user(cls, v):
        if isinstance(v, str):
            return Path(v).expanduser()
        if isinstance(v, Path):
            return v.expanduser()
        return v


class AppConfig(BaseModel):
    audio: AudioConfig = Field(default_factory=AudioConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    nlu: NLUConfig = Field(default_factory=NLUConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
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
