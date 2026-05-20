from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.core.types import Intent


def _intent(name="open_app", slots=None, confidence=1.0):
    return Intent(name=name, slots=slots or {"app": "telegram"},
                  confidence=confidence)


class _FakeClock:
    def __init__(self, start=1000.0):
        self.now = start
    def __call__(self):
        return self.now


def test_add_stores_eligible_intent():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(_intent())
    entity = store.get_recent_entity()
    assert entity == ("telegram", "app")


def test_add_skips_unknown():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent.unknown())
    assert store.get_recent_entity() is None


def test_add_skips_confirm_yes():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="confirm_yes", slots={}, confidence=1.0))
    assert store.get_recent_entity() is None


def test_add_skips_slotless():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="minimize_all", slots={}, confidence=1.0))
    assert store.get_recent_entity() is None


def test_get_recent_entity_returns_newest():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(_intent(slots={"app": "telegram"}))
    store.add(_intent(slots={"app": "chrome"}))
    entity = store.get_recent_entity()
    assert entity == ("chrome", "app")


def test_get_recent_entity_returns_none_when_empty():
    store = ContextStore(max_size=5, ttl_s=60.0)
    assert store.get_recent_entity() is None


def test_get_recent_entity_respects_ttl():
    clock = _FakeClock(start=1000.0)
    store = ContextStore(max_size=5, ttl_s=60.0, clock=clock)
    store.add(_intent(slots={"app": "telegram"}))
    # Advance past TTL
    clock.now = 1100.0
    assert store.get_recent_entity() is None


def test_get_recent_entity_respects_slot_priority():
    store = ContextStore(max_size=5, ttl_s=60.0)
    # Intent with both app and name — app wins
    store.add(Intent(name="X", slots={"name": "n1", "app": "a1"},
                     confidence=1.0))
    entity = store.get_recent_entity()
    assert entity == ("a1", "app")


def test_get_recent_entity_prefers_name_when_no_app():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="open_path", slots={"name": "downloads"},
                     confidence=1.0))
    entity = store.get_recent_entity()
    assert entity == ("downloads", "name")


def test_get_recent_entity_prefers_query_over_url():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="web_search",
                     slots={"url": "x.com", "query": "weather"},
                     confidence=1.0))
    entity = store.get_recent_entity()
    assert entity == ("weather", "query")


def test_deque_evicts_oldest_at_max_size():
    store = ContextStore(max_size=2, ttl_s=60.0)
    store.add(_intent(slots={"app": "one"}))
    store.add(_intent(slots={"app": "two"}))
    store.add(_intent(slots={"app": "three"}))
    # max_size=2 → "one" evicted, "three" is newest
    entity = store.get_recent_entity()
    assert entity == ("three", "app")


def test_clear_empties_store():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(_intent())
    store.clear()
    assert store.get_recent_entity() is None


def test_skip_intent_with_non_string_slot():
    """volume_set has level=int — not a usable entity for pronoun resolution."""
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="volume_set", slots={"level": 50}, confidence=1.0))
    # No string slot in priority order → no entity
    assert store.get_recent_entity() is None


def test_skip_intent_with_empty_string_slot():
    store = ContextStore(max_size=5, ttl_s=60.0)
    store.add(Intent(name="open_app", slots={"app": "   "}, confidence=1.0))
    assert store.get_recent_entity() is None
