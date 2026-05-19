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
