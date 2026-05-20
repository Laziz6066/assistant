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


# Regression: specific literal-prefix rules (open_path, close_window, etc.) MUST
# win over the generic open_app/close_app catch-alls. Earlier the YAML listed
# open_app first, so the greedy `.+?` slot captured "папку загрузки" and routed
# to open_app instead of open_path.
SPECIFIC_BEFORE_GENERIC = textwrap.dedent("""
- intent: open_path
  examples: ["открой папку {name}", "открой директорию {name}"]
  slots: {name: string}
- intent: open_bookmark
  examples: ["открой закладку {name}"]
  slots: {name: string}
- intent: open_url
  examples: ["открой сайт {url}"]
  slots: {url: string}
- intent: open_app
  examples: ["открой {app}", "запусти {app}"]
  slots: {app: string}
- intent: close_window
  examples: ["закрой текущее окно", "закрой окно"]
  slots: {}
- intent: close_app
  examples: ["закрой приложение {app}", "закрой {app}"]
  slots: {app: string}
""")


@pytest.fixture
def ordered_router(tmp_path):
    f = tmp_path / "commands.yaml"
    f.write_text(SPECIFIC_BEFORE_GENERIC, encoding="utf-8")
    return RulesRouter(commands_path=f, fuzzy_threshold=85)


def test_specific_prefix_rules_win_over_generic_open_app(ordered_router):
    """'открой папку загрузки' must route to open_path, not open_app."""
    i = ordered_router.route(_t("открой папку загрузки"))
    assert i.name == "open_path"
    assert i.slots == {"name": "загрузки"}


def test_open_bookmark_wins_over_open_app(ordered_router):
    """'открой закладку ютуб' must route to open_bookmark."""
    i = ordered_router.route(_t("открой закладку ютуб"))
    assert i.name == "open_bookmark"
    assert i.slots == {"name": "ютуб"}


def test_open_url_wins_over_open_app(ordered_router):
    """'открой сайт github' must route to open_url."""
    i = ordered_router.route(_t("открой сайт github"))
    assert i.name == "open_url"
    assert i.slots == {"url": "github"}


def test_close_window_wins_over_close_app(ordered_router):
    """'закрой текущее окно' must route to close_window, not close_app."""
    i = ordered_router.route(_t("закрой текущее окно"))
    assert i.name == "close_window"


def test_close_app_still_matches_after_close_window(ordered_router):
    """Generic close_app still works when no literal prefix matches."""
    i = ordered_router.route(_t("закрой telegram"))
    assert i.name == "close_app"
    assert i.slots == {"app": "telegram"}


def test_open_app_still_matches_generic_form(ordered_router):
    """Generic open_app still works when no literal prefix matches."""
    i = ordered_router.route(_t("открой telegram"))
    assert i.name == "open_app"
    assert i.slots == {"app": "telegram"}
