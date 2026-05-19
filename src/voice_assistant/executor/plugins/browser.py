from __future__ import annotations
import webbrowser
from urllib.parse import quote_plus
from voice_assistant.executor.registry import Registry
from voice_assistant.core.types import ExecutionResult


def register(reg: Registry) -> None:
    def web_search(slots, ctx) -> ExecutionResult:
        q = slots.get("query", "").strip()
        if not q:
            return ExecutionResult.fail("empty query", "Что искать?")
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(q)}")
        return ExecutionResult.ok(f"searched {q}", f"Ищу {q}")

    def open_url(slots, ctx) -> ExecutionResult:
        url = slots.get("url", "").strip()
        if not url:
            return ExecutionResult.fail("empty url", "Какой адрес?")
        if url.startswith(("http://", "https://")):
            pass
        elif ":" in url.split("/", 1)[0]:
            return ExecutionResult.fail(
                f"unsafe url scheme: {url!r}", "Не могу открыть этот адрес")
        else:
            url = "https://" + url
        webbrowser.open(url)
        return ExecutionResult.ok(f"opened {url}", "Открываю")

    def open_bookmark(slots, ctx) -> ExecutionResult:
        url = ctx.resolve_bookmark(slots.get("name", ""))
        if not url:
            return ExecutionResult.fail("unknown bookmark", "Нет такой закладки")
        webbrowser.open(url)
        return ExecutionResult.ok(f"opened {url}", "Открываю")

    reg.add("web_search", web_search)
    reg.add("open_url", open_url)
    reg.add("open_bookmark", open_bookmark)
