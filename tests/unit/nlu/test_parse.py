from voice_assistant.nlu.parse import parse_and_validate
from voice_assistant.core.types import Intent


_CATALOG = {
    "open_app":     {"slots": [("app", "string")]},
    "volume_set":   {"slots": [("level", "int")]},
    "minimize_all": {"slots": []},
}


def test_parse_valid_open_app():
    content = '{"intent": "open_app", "slots": {"app": "telegram"}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "open_app"
    assert intent.slots == {"app": "telegram"}
    assert abs(intent.confidence - 0.9) < 1e-6


def test_parse_valid_slotless_intent():
    content = '{"intent": "minimize_all", "slots": {}, "confidence": 0.85}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "minimize_all"
    assert intent.slots == {}


def test_parse_int_slot_coerced_from_string():
    content = '{"intent": "volume_set", "slots": {"level": "20"}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "volume_set"
    assert intent.slots == {"level": 20}
    assert isinstance(intent.slots["level"], int)


def test_parse_int_slot_accepts_integer_already():
    content = '{"intent": "volume_set", "slots": {"level": 30}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.slots == {"level": 30}


def test_parse_string_slot_stripped():
    content = '{"intent": "open_app", "slots": {"app": "  telegram  "}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.slots == {"app": "telegram"}


def test_parse_unknown_response_returns_unknown():
    content = '{"intent": "unknown", "slots": {}, "confidence": 0.0}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_invalid_json_returns_unknown():
    intent = parse_and_validate("not json", _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_missing_intent_key_returns_unknown():
    intent = parse_and_validate('{"slots": {}, "confidence": 0.9}',
                                  _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_hallucinated_intent_returns_unknown():
    content = '{"intent": "make_coffee", "slots": {}, "confidence": 0.99}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_low_confidence_returns_unknown():
    content = '{"intent": "open_app", "slots": {"app": "x"}, "confidence": 0.4}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_missing_required_slot_returns_unknown():
    content = '{"intent": "open_app", "slots": {}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_uncoercible_int_slot_returns_unknown():
    content = '{"intent": "volume_set", "slots": {"level": "loud"}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_non_dict_slots_returns_unknown():
    content = '{"intent": "open_app", "slots": "telegram", "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_confidence_at_threshold_accepted():
    content = '{"intent": "minimize_all", "slots": {}, "confidence": 0.5}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "minimize_all"


def test_dict_slot_value_returns_unknown():
    """LLM hallucinated nested dict as slot value — reject."""
    content = '{"intent": "open_app", "slots": {"app": {"x": "y"}}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_null_slot_value_returns_unknown():
    """LLM emitted null/None for a required slot — reject."""
    content = '{"intent": "open_app", "slots": {"app": null}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"


def test_list_slot_value_returns_unknown():
    """LLM emitted a list as slot value — reject."""
    content = '{"intent": "open_app", "slots": {"app": ["a","b"]}, "confidence": 0.9}'
    intent = parse_and_validate(content, _CATALOG, min_confidence=0.5)
    assert intent.name == "unknown"
