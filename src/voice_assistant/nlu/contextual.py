from __future__ import annotations
import re
from dataclasses import replace

from loguru import logger

from voice_assistant.nlu.base import NLURouter
from voice_assistant.nlu.context_store import ContextStore
from voice_assistant.core.types import Transcript, Intent


_PRONOUNS: tuple[str, ...] = (
    "его", "её", "ее", "их",
    "это", "этот", "эту", "этого", "этому",
    "тот", "та", "то", "того", "тому", "ту",
    "it", "this", "that",
)

_PRONOUN_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in _PRONOUNS) + r")\b",
    flags=re.IGNORECASE,
)


class ContextualRouter(NLURouter):
    """NLURouter that rewrites pronouns to the most recent entity from
    `ContextStore` before delegating to an inner router.

    If `store` is None, or the store has no eligible context, the original
    transcript is passed through unchanged.
    """

    def __init__(self, inner: NLURouter,
                 store: ContextStore | None) -> None:
        self._inner = inner
        self._store = store

    def route(self, transcript: Transcript) -> Intent:
        rewritten = self._rewrite(transcript.text)
        if rewritten == transcript.text:
            return self._inner.route(transcript)
        logger.debug(f"context rewrite: {transcript.text!r} → {rewritten!r}")
        return self._inner.route(replace(transcript, text=rewritten))

    def _rewrite(self, text: str) -> str:
        if self._store is None:
            return text
        if not _PRONOUN_RE.search(text):
            return text
        entity = self._store.get_recent_entity()
        if entity is None:
            return text
        value, _slot = entity
        return _PRONOUN_RE.sub(value, text)
