from unittest.mock import MagicMock
import pytest

from voice_assistant.nlu.contextual import ContextualRouter
from voice_assistant.nlu.base import NLURouter
from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.core.types import Transcript, Intent


def _t(text):
    return Transcript(text=text, language="ru", confidence=0.9,
                       duration_ms=500)


def _mock_inner(return_intent):
    inner = MagicMock(spec=NLURouter)
    inner.route.return_value = return_intent
    return inner


def test_passthrough_when_no_pronouns():
    inner = _mock_inner(Intent("open_app", {"app": "x"}, 1.0))
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("открой блокнот"))
    args, _ = inner.route.call_args
    assert args[0].text == "открой блокнот"


def test_passthrough_when_store_empty():
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("закрой его"))
    args, _ = inner.route.call_args
    assert args[0].text == "закрой его"


def test_passthrough_when_store_none():
    inner = _mock_inner(Intent.unknown())
    router = ContextualRouter(inner=inner, store=None)
    router.route(_t("закрой его"))
    args, _ = inner.route.call_args
    assert args[0].text == "закрой его"


def test_rewrite_replaces_simple_pronoun():
    inner = _mock_inner(Intent("close_app", {"app": "telegram"}, 1.0))
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("закрой его"))
    args, _ = inner.route.call_args
    assert args[0].text == "закрой telegram"


def test_rewrite_replaces_multiple_pronouns_with_same_entity():
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "chrome"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("открой его и сверни это"))
    args, _ = inner.route.call_args
    assert args[0].text == "открой chrome и сверни chrome"


@pytest.mark.parametrize("pronoun", [
    "его", "её", "ее", "их",
    "это", "этот", "эту", "этого", "этому",
    "тот", "та", "то", "того", "тому", "ту",
])
def test_each_russian_pronoun_recognized(pronoun):
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "X"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t(f"закрой {pronoun}"))
    args, _ = inner.route.call_args
    assert "X" in args[0].text


@pytest.mark.parametrize("pronoun", ["it", "this", "that"])
def test_each_english_pronoun_recognized(pronoun):
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "X"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t(f"close {pronoun}"))
    args, _ = inner.route.call_args
    assert "X" in args[0].text


def test_case_insensitive_match():
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("Закрой ЕГО"))
    args, _ = inner.route.call_args
    assert "telegram" in args[0].text.lower()


def test_word_boundary_prevents_partial_match():
    """The pronoun 'это' must not match inside 'этузиазм'."""
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("этузиазм"))
    args, _ = inner.route.call_args
    assert args[0].text == "этузиазм"


def test_expired_context_treated_as_empty():
    inner = _mock_inner(Intent.unknown())
    clock = {"now": 1000.0}
    store = ContextStore(max_size=5, ttl_s=60.0, clock=lambda: clock["now"])
    store.add(Intent("open_app", {"app": "telegram"}, 1.0))
    clock["now"] = 1100.0  # past TTL
    router = ContextualRouter(inner=inner, store=store)
    router.route(_t("закрой его"))
    args, _ = inner.route.call_args
    assert args[0].text == "закрой его"


def test_inner_router_exception_propagates():
    inner = MagicMock(spec=NLURouter)
    inner.route.side_effect = RuntimeError("boom")
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "X"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    with pytest.raises(RuntimeError, match="boom"):
        router.route(_t("закрой его"))


def test_rewritten_transcript_preserves_metadata():
    inner = _mock_inner(Intent.unknown())
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent("open_app", {"app": "X"}, 1.0))
    router = ContextualRouter(inner=inner, store=store)
    original = Transcript(text="закрой его", language="ru",
                           confidence=0.87, duration_ms=421)
    router.route(original)
    args, _ = inner.route.call_args
    inner_t = args[0]
    assert inner_t.language == "ru"
    assert inner_t.confidence == 0.87
    assert inner_t.duration_ms == 421
    assert "X" in inner_t.text
