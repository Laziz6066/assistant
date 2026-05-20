from unittest.mock import MagicMock
from pathlib import Path

from voice_assistant.nlu.llm_fallback import LLMFallbackRouter
from voice_assistant.nlu.base import NLURouter
from voice_assistant.core.types import Transcript, Intent


def _write_commands(tmp_path: Path) -> Path:
    p = tmp_path / "commands.yaml"
    p.write_text(
        '- intent: open_app\n'
        '  examples: ["открой {app}"]\n'
        '  slots: {app: string}\n'
        '- intent: minimize_all\n'
        '  examples: ["сверни всё"]\n'
        '  slots: {}\n', encoding="utf-8")
    return p


def test_primary_known_intent_bypasses_llm(tmp_path):
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent("open_app", {"app": "telegram"}, 1.0)
    client = MagicMock()
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={})
    intent = router.route(Transcript("открой telegram", "ru", 0.9, 100))
    assert intent.name == "open_app"
    client.classify.assert_not_called()


def test_primary_unknown_calls_llm(tmp_path):
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent.unknown()
    client = MagicMock()
    client.classify.return_value = Intent("open_app", {"app": "telegram"}, 0.9)
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={})
    intent = router.route(Transcript("запусти телегу", "ru", 0.9, 100))
    assert intent.name == "open_app"
    client.classify.assert_called_once()
    # Verify it got the transcript text and the prepared system prompt
    args, kwargs = client.classify.call_args
    # Should be either positional or kw; check both shapes
    call_text = kwargs.get("text") or args[0]
    assert call_text == "запусти телегу"


def test_empty_transcript_does_not_call_llm(tmp_path):
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent.unknown()
    client = MagicMock()
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={})
    intent = router.route(Transcript("   ", "ru", 0.9, 100))
    assert intent.name == "unknown"
    client.classify.assert_not_called()


def test_llm_returns_unknown_propagates(tmp_path):
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent.unknown()
    client = MagicMock()
    client.classify.return_value = Intent.unknown()
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={})
    intent = router.route(Transcript("ерунда какая-то", "ru", 0.9, 100))
    assert intent.name == "unknown"


def test_system_prompt_built_at_init(tmp_path):
    """Prompt is assembled once at __init__ and contains catalog intents."""
    primary = MagicMock(spec=NLURouter)
    primary.route.return_value = Intent.unknown()
    client = MagicMock()
    client.classify.return_value = Intent.unknown()
    router = LLMFallbackRouter(primary=primary, client=client,
                                commands_path=_write_commands(tmp_path),
                                app_aliases={"телега": "telegram"})
    assert "open_app" in router._system_prompt
    assert "minimize_all" in router._system_prompt
    assert "телега" in router._system_prompt
