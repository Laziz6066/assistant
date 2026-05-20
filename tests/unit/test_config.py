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


from voice_assistant.config import LLMConfig


def test_llm_config_default_values():
    cfg = LLMConfig()
    assert cfg.enabled is False
    assert cfg.model == "qwen2.5:3b-instruct"
    assert cfg.host == "http://localhost:11434"
    assert cfg.timeout_s == 3.0
    assert cfg.temperature == 0.1
    assert cfg.min_confidence == 0.5


def test_llm_config_accepts_overrides():
    cfg = LLMConfig(enabled=True, model="llama3.2:3b",
                    timeout_s=5.0, min_confidence=0.7)
    assert cfg.enabled is True
    assert cfg.model == "llama3.2:3b"
    assert cfg.timeout_s == 5.0
    assert cfg.min_confidence == 0.7


def test_app_config_has_llm_section_with_defaults():
    cfg = AppConfig()
    assert cfg.llm.enabled is False
    assert cfg.llm.model == "qwen2.5:3b-instruct"


from voice_assistant.config import WakeConfig


def test_wake_config_default_values():
    cfg = WakeConfig()
    assert cfg.enabled is False
    assert cfg.model == "hey_jarvis"
    assert cfg.threshold == 0.5
    assert cfg.silence_ms == 800
    assert cfg.max_speech_ms == 10000
    assert cfg.models_dir.is_absolute()
    assert cfg.models_dir.parts[-2:] == (".voice-assistant", "wake-models")


def test_wake_config_expands_tilde_in_models_dir():
    cfg = WakeConfig(models_dir="~/custom/wake")
    assert str(cfg.models_dir).startswith(str(Path.home()))
    assert cfg.models_dir.parts[-2:] == ("custom", "wake")


def test_wake_config_accepts_overrides():
    cfg = WakeConfig(enabled=True, model="alexa", threshold=0.7,
                    silence_ms=500, max_speech_ms=15000)
    assert cfg.enabled is True
    assert cfg.model == "alexa"
    assert cfg.threshold == 0.7
    assert cfg.silence_ms == 500
    assert cfg.max_speech_ms == 15000


def test_app_config_has_wake_section_with_defaults():
    cfg = AppConfig()
    assert cfg.wake.enabled is False
    assert cfg.wake.model == "hey_jarvis"


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


from voice_assistant.config import DialogConfig


def test_dialog_config_default_values():
    cfg = DialogConfig()
    assert cfg.enabled is True
    assert cfg.context_ttl_s == 60.0
    assert cfg.context_size == 5


def test_dialog_config_accepts_overrides():
    cfg = DialogConfig(enabled=False, context_ttl_s=30.0, context_size=10)
    assert cfg.enabled is False
    assert cfg.context_ttl_s == 30.0
    assert cfg.context_size == 10


def test_app_config_has_dialog_section_default_enabled():
    cfg = AppConfig()
    assert cfg.dialog.enabled is True
    assert cfg.dialog.context_ttl_s == 60.0
