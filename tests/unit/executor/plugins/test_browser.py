from unittest.mock import MagicMock, patch
from voice_assistant.executor.registry import Registry
from voice_assistant.executor.context import ExecutorContext
from voice_assistant.config import AppConfig
from voice_assistant.core.types import Intent
import voice_assistant.executor.plugins.browser as br


def _ctx(bookmarks=None):
    return ExecutorContext(config=AppConfig(bookmarks=bookmarks or {}),
                           platform_ops=MagicMock())


def test_web_search_opens_google_query():
    reg = Registry()
    br.register(reg)
    with patch.object(br.webbrowser, "open") as op:
        res = reg.dispatch(Intent("web_search", {"query": "погода завтра"}), _ctx())
    url = op.call_args[0][0]
    assert "google.com/search" in url and "%D0" in url  # url-encoded cyrillic
    assert res.success


def test_open_url_normalizes_scheme():
    reg = Registry()
    br.register(reg)
    with patch.object(br.webbrowser, "open") as op:
        reg.dispatch(Intent("open_url", {"url": "example.com"}), _ctx())
    assert op.call_args[0][0] == "https://example.com"


def test_open_bookmark_uses_config():
    reg = Registry()
    br.register(reg)
    ctx = _ctx(bookmarks={"ютуб": "https://youtube.com"})
    with patch.object(br.webbrowser, "open") as op:
        res = reg.dispatch(Intent("open_bookmark", {"name": "ютуб"}), ctx)
    assert op.call_args[0][0] == "https://youtube.com"
    assert res.success


def test_unknown_bookmark_fails():
    reg = Registry()
    br.register(reg)
    res = reg.dispatch(Intent("open_bookmark", {"name": "несуществует"}), _ctx())
    assert res.success is False


def test_open_url_rejects_dangerous_schemes():
    reg = Registry()
    br.register(reg)
    for bad in ("file:///C:/Windows/system32", "javascript:alert(1)", "data:text/html,x"):
        with patch.object(br.webbrowser, "open") as op:
            res = reg.dispatch(Intent("open_url", {"url": bad}), _ctx())
        op.assert_not_called()
        assert res.success is False
