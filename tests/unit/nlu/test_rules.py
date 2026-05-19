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
