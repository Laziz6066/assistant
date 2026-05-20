import textwrap
from pathlib import Path
import pytest
from voice_assistant.config import load_config, AppConfig, TTSConfig


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


def test_tts_config_default_values():
    cfg = TTSConfig()
    assert cfg.enabled is True
    assert cfg.voice == "ru_RU-irina-medium"
    assert cfg.length_scale == 1.0
    # Default voices_dir is an absolute home-relative path
    assert cfg.voices_dir.is_absolute()
    assert cfg.voices_dir.parts[-2:] == (".voice-assistant", "voices")


def test_tts_config_expands_tilde_in_voices_dir():
    cfg = TTSConfig(voices_dir="~/custom/voices")
    assert str(cfg.voices_dir).startswith(str(Path.home()))
    assert cfg.voices_dir.parts[-2:] == ("custom", "voices")


def test_tts_config_accepts_absolute_path():
    abs_path = Path.cwd() / "some" / "voices"
    cfg = TTSConfig(voices_dir=str(abs_path))
    assert cfg.voices_dir == abs_path


def test_app_config_has_tts_section_with_defaults():
    cfg = AppConfig()
    assert cfg.tts.enabled is True
    assert cfg.tts.voice == "ru_RU-irina-medium"
