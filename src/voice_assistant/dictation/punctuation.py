from __future__ import annotations
import re


_PUNCT: dict[str, str] = {
    # Multi-word phrases must be applied first; we sort by length
    # descending below to handle that.
    "точка с запятой": ";",
    "восклицательный знак": "!",
    "новая строка": "\n",
    # Single-word
    "точка": ".",
    "запятая": ",",
    "вопрос": "?",
    "восклицательный": "!",
    "двоеточие": ":",
    "тире": "—",
    "дефис": "-",
}


def normalize_punctuation(text: str) -> str:
    """Replace Russian punctuation words with their symbols and tighten
    whitespace around the results.

    Word-boundary matching prevents partial-word collisions (e.g.,
    'точки' is NOT replaced — only the exact word 'точка' is).
    """
    if not text:
        return ""
    out = text
    # Longest phrases first so multi-word entries win over single-word.
    for word in sorted(_PUNCT.keys(), key=len, reverse=True):
        symbol = _PUNCT[word]
        out = re.sub(rf"\b{re.escape(word)}\b", symbol, out,
                      flags=re.IGNORECASE)
    # Remove space immediately before standard punctuation.
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    # Tighten newlines.
    out = re.sub(r"\s+\n", "\n", out)
    out = re.sub(r"\n\s+", "\n", out)
    # Collapse runs of horizontal whitespace.
    out = re.sub(r"[ \t]+", " ", out)
    return out.strip()
