import time
from unittest.mock import MagicMock, patch
import pytest

from voice_assistant.nlu.ollama_client import OllamaClient
from voice_assistant.core.types import Intent


_CATALOG = {
    "open_app":     {"slots": [("app", "string")]},
    "minimize_all": {"slots": []},
}


def _make_chat_response(content: str):
    """Build a fake ollama.ChatResponse-like object whose .message.content
    returns the given string. ollama's library accepts either attribute or
    dict access; the simplest mockable shape is an object with .message.content.
    """
    resp = MagicMock()
    resp.message.content = content
    return resp


def _make_client(timeout_s=3.0, min_conf=0.5):
    with patch("voice_assistant.nlu.ollama_client.ollama.Client"):
        return OllamaClient(
            host="http://localhost:11434",
            model="qwen2.5:3b-instruct",
            timeout_s=timeout_s,
            temperature=0.1,
            min_confidence=min_conf,
        )


def test_classify_happy_path_returns_intent():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response(
        '{"intent": "open_app", "slots": {"app": "telegram"}, "confidence": 0.9}'
    ))
    intent = client.classify("запусти телегу", "system prompt", _CATALOG)
    assert intent.name == "open_app"
    assert intent.slots == {"app": "telegram"}


def test_classify_passes_messages_and_format_json():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response(
        '{"intent": "minimize_all", "slots": {}, "confidence": 0.9}'
    ))
    client.classify("сверни всё", "my system prompt", _CATALOG)
    args, kwargs = client._client.chat.call_args
    assert kwargs["model"] == "qwen2.5:3b-instruct"
    assert kwargs["format"] == "json"
    msgs = kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "my system prompt"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "сверни всё"
    assert kwargs["options"]["temperature"] == 0.1
    assert kwargs.get("keep_alive") == "5m"


def test_classify_connection_error_marks_unreachable_60s():
    import httpx
    client = _make_client()
    client._client.chat = MagicMock(side_effect=httpx.ConnectError("no route"))
    with patch("voice_assistant.nlu.ollama_client.time.monotonic",
                return_value=1000.0):
        intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"
    # _unreachable_until = mono + 60
    assert client._unreachable_until == pytest.approx(1060.0, abs=0.1)


def test_classify_short_circuits_when_unreachable_cache_active():
    client = _make_client()
    client._client.chat = MagicMock()
    client._unreachable_until = 1e18  # essentially forever
    intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"
    client._client.chat.assert_not_called()


def test_classify_retries_after_unreachable_window_expires():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response(
        '{"intent": "minimize_all", "slots": {}, "confidence": 0.9}'
    ))
    # Set unreachable in the past
    with patch("voice_assistant.nlu.ollama_client.time.monotonic",
                return_value=1000.0):
        client._unreachable_until = 999.0
        intent = client.classify("сверни", "prompt", _CATALOG)
    assert intent.name == "minimize_all"
    client._client.chat.assert_called_once()


def test_classify_model_not_found_marks_permanent_unreachable():
    import ollama
    client = _make_client()
    err = ollama.ResponseError("model 'x' not found", status_code=404)
    client._client.chat = MagicMock(side_effect=err)
    with patch("voice_assistant.nlu.ollama_client.time.monotonic",
                return_value=1000.0):
        intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"
    # Permanent: very large value
    assert client._unreachable_until > 1e8


def test_classify_timeout_returns_unknown_without_caching():
    import httpx
    client = _make_client()
    client._client.chat = MagicMock(side_effect=httpx.ReadTimeout("slow"))
    with patch("voice_assistant.nlu.ollama_client.time.monotonic",
                return_value=1000.0):
        client._unreachable_until = 0
        intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"
    # Timeout is normal — does NOT cache unreachable
    assert client._unreachable_until == 0


def test_classify_generic_exception_returns_unknown():
    client = _make_client()
    client._client.chat = MagicMock(side_effect=RuntimeError("boom"))
    intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"


def test_classify_invalid_json_returns_unknown():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response("not json"))
    intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"


def test_classify_hallucinated_intent_returns_unknown():
    client = _make_client()
    client._client.chat = MagicMock(return_value=_make_chat_response(
        '{"intent": "make_coffee", "slots": {}, "confidence": 0.99}'
    ))
    intent = client.classify("hi", "prompt", _CATALOG)
    assert intent.name == "unknown"


def test_warning_logged_once_for_connection_error(caplog):
    import httpx
    client = _make_client()
    client._client.chat = MagicMock(side_effect=httpx.ConnectError("nope"))
    # First call: should mark unreachable, log warning
    client._unreachable_until = 0
    client.classify("hi", "prompt", _CATALOG)
    # Verify the warning flag was set so a second similar call won't re-warn
    assert client._warned_unreachable is True
