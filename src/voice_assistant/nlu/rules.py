from __future__ import annotations
import re
from pathlib import Path
import yaml
from rapidfuzz import fuzz
from voice_assistant.nlu.base import NLURouter
from voice_assistant.core.types import Transcript, Intent

_SLOT_RE = re.compile(r"\{(\w+)(?::(\w+))?\}")


def _compile(example: str) -> tuple[re.Pattern, list[tuple[str, str]]]:
    """Compile an example template into regex and slot metadata.

    Example: "открой {app}" -> regex for "открой <app_text>" + slots=[("app", "string")]
    Example: "громкость {level:int}" -> regex for "громкость <int>" + slots=[("level", "int")]
    """
    slots: list[tuple[str, str]] = []
    pattern = "^"
    pos = 0
    for m in _SLOT_RE.finditer(example):
        # Add literal text before the slot
        pattern += re.escape(example[pos:m.start()])
        name, typ = m.group(1), m.group(2) or "string"
        slots.append((name, typ))
        # Add slot pattern: digits for int, any non-greedy for string
        pattern += r"(\d+)" if typ == "int" else r"(.+?)"
        pos = m.end()
    # Add remaining literal text
    pattern += re.escape(example[pos:]) + "$"
    return re.compile(pattern, re.IGNORECASE), slots


class RulesRouter(NLURouter):
    """Rule-based NLU router with fuzzy fallback for slotless intents."""

    def __init__(self, commands_path: str | Path, fuzzy_threshold: int = 85):
        """Load rules from a YAML commands file.

        Args:
            commands_path: Path to commands.yaml file
            fuzzy_threshold: Minimum fuzzy match score (0-100) for slotless intents
        """
        raw = yaml.safe_load(Path(commands_path).read_text(encoding="utf-8")) or []
        self.fuzzy_threshold = fuzzy_threshold
        self._rules = []  # list of (intent, regex, slots, literal_template)

        for entry in raw:
            for ex in entry.get("examples", []):
                rx, slots = _compile(ex)
                # For fuzzy fallback: remove slots from template to get literal text
                literal = _SLOT_RE.sub("", ex).strip()
                self._rules.append((entry["intent"], rx, slots, literal))

    def _coerce(self, value: str, typ: str) -> int | str:
        """Coerce captured string value to the correct type."""
        return int(value) if typ == "int" else value.strip()

    def route(self, transcript: Transcript) -> Intent:
        """Route a transcript to an intent.

        1. Try exact regex match (with slot extraction)
        2. Fall back to fuzzy match on slotless intents
        3. Return unknown intent if no match
        """
        text = transcript.text.strip().lower()
        if not text:
            return Intent.unknown()

        # Try exact regex matches first
        for intent, rx, slots, _ in self._rules:
            m = rx.match(text)
            if m:
                # Extract and coerce slot values
                values = {n: self._coerce(g, t)
                          for (n, t), g in zip(slots, m.groups())}
                return Intent(name=intent, slots=values, confidence=1.0)

        # Fuzzy match on slotless rules
        best, best_score = None, 0
        for intent, _, slots, literal in self._rules:
            # Only consider slotless intents for fuzzy matching
            if slots or not literal:
                continue
            score = fuzz.ratio(text, literal.lower())
            if score > best_score:
                best, best_score = intent, score

        if best and best_score >= self.fuzzy_threshold:
            return Intent(name=best, slots={}, confidence=best_score / 100.0)

        return Intent.unknown()
