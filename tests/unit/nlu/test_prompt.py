from pathlib import Path
import pytest
from voice_assistant.nlu.prompt import load_catalog, build_system_prompt


def _write_commands(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "commands.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_load_catalog_collects_intents_with_slots(tmp_path):
    p = _write_commands(tmp_path,
        '- intent: open_app\n'
        '  examples: ["открой {app}"]\n'
        '  slots: {app: string}\n'
        '- intent: volume_set\n'
        '  examples: ["громкость {level:int}"]\n'
        '  slots: {level: int}\n'
        '- intent: minimize_all\n'
        '  examples: ["сверни всё"]\n'
        '  slots: {}\n')
    catalog = load_catalog(p)
    assert "open_app" in catalog
    assert catalog["open_app"]["slots"] == [("app", "string")]
    assert catalog["volume_set"]["slots"] == [("level", "int")]
    assert catalog["minimize_all"]["slots"] == []


def test_load_catalog_dedupes_intent_across_multiple_examples(tmp_path):
    # If the same intent appears once with the same slots, no duplicate
    p = _write_commands(tmp_path,
        '- intent: open_app\n'
        '  examples: ["открой {app}", "запусти {app}"]\n'
        '  slots: {app: string}\n')
    catalog = load_catalog(p)
    assert list(catalog.keys()) == ["open_app"]
    assert catalog["open_app"]["slots"] == [("app", "string")]


def test_build_system_prompt_lists_every_intent():
    catalog = {
        "open_app":     {"slots": [("app", "string")]},
        "minimize_all": {"slots": []},
        "volume_set":   {"slots": [("level", "int")]},
    }
    prompt = build_system_prompt(catalog, app_aliases={})
    assert "open_app" in prompt
    assert "minimize_all" in prompt
    assert "volume_set" in prompt
    # int slot type annotated
    assert "int" in prompt
    # JSON contract present
    assert '"intent"' in prompt
    assert '"slots"' in prompt
    assert '"confidence"' in prompt
    # Unknown-fallback rule present
    assert "unknown" in prompt.lower()


def test_build_system_prompt_includes_aliases_when_present():
    catalog = {"open_app": {"slots": [("app", "string")]}}
    prompt = build_system_prompt(catalog,
                                  app_aliases={"телега": "telegram",
                                               "браузер": "chrome"})
    assert "телега" in prompt
    assert "telegram" in prompt
    assert "браузер" in prompt
    assert "chrome" in prompt


def test_build_system_prompt_omits_alias_block_when_empty():
    catalog = {"open_app": {"slots": [("app", "string")]}}
    prompt = build_system_prompt(catalog, app_aliases={})
    # No alias section should appear
    assert "Алиасы" not in prompt and "alias" not in prompt.lower()
