from __future__ import annotations
from pathlib import Path

from voice_assistant.nlu.base import NLURouter
from voice_assistant.nlu.ollama_client import OllamaClient
from voice_assistant.nlu.prompt import load_catalog, build_system_prompt
from voice_assistant.core.types import Transcript, Intent


class LLMFallbackRouter(NLURouter):
    """NLURouter that consults a local LLM when the primary returns unknown.

    Composition pattern: wraps an existing NLURouter (e.g. RulesRouter).
    Rules-known commands skip the LLM entirely; only `unknown` results
    trigger the slow path.
    """

    def __init__(self, primary: NLURouter, client: OllamaClient,
                 commands_path: Path | str,
                 app_aliases: dict[str, str]) -> None:
        self._primary = primary
        self._client = client
        self._catalog = load_catalog(commands_path)
        self._system_prompt = build_system_prompt(self._catalog, app_aliases)

    def route(self, transcript: Transcript) -> Intent:
        primary_intent = self._primary.route(transcript)
        if primary_intent.name != "unknown":
            return primary_intent
        if not transcript.text.strip():
            return primary_intent
        return self._client.classify(
            text=transcript.text,
            system_prompt=self._system_prompt,
            catalog=self._catalog,
        )
