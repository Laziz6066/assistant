from __future__ import annotations
from pathlib import Path
import yaml


def load_catalog(commands_path: Path | str) -> dict[str, dict]:
    """Load commands.yaml into a flat catalog: intent_name -> {slots: [(name, type), ...]}.

    Duplicates of the same intent across multiple yaml entries are collapsed —
    first occurrence wins (matching RulesRouter behaviour).
    """
    raw = yaml.safe_load(Path(commands_path).read_text(encoding="utf-8")) or []
    catalog: dict[str, dict] = {}
    for entry in raw:
        name = entry["intent"]
        if name in catalog:
            continue
        slots_field = entry.get("slots") or {}
        slots = [(k, v) for k, v in slots_field.items()]
        catalog[name] = {"slots": slots}
    return catalog


def _format_intent_line(name: str, slots: list[tuple[str, str]]) -> str:
    if not slots:
        return f"- {name} — без slots."
    slot_descs = ", ".join(f"{n} ({t})" for n, t in slots)
    return f"- {name} — slots: {slot_descs}."


def build_system_prompt(catalog: dict[str, dict],
                         app_aliases: dict[str, str]) -> str:
    """Assemble the system prompt from the live catalog.

    The intent list is generated from `catalog`; aliases are appended when
    non-empty. Keep examples static — they're crafted to teach the model the
    JSON contract.
    """
    intent_lines = "\n".join(_format_intent_line(n, c["slots"])
                              for n, c in catalog.items())

    alias_block = ""
    if app_aliases:
        pairs = ", ".join(f"{k}→{v}" for k, v in app_aliases.items())
        alias_block = f"\n\nАлиасы приложений: {pairs}"

    return f"""\
Ты — классификатор голосовых команд для ПК-ассистента. Пользователь говорит фразу на русском, ты определяешь намерение и параметры.

Доступные намерения (intents):
{intent_lines}{alias_block}

Правила:
1. Отвечай ТОЛЬКО валидным JSON в формате: {{"intent": "<name>", "slots": {{}}, "confidence": <0.0-1.0>}}
2. Если фраза не подходит ни под один intent — верни {{"intent": "unknown", "slots": {{}}, "confidence": 0.0}}
3. Confidence ≥ 0.7 если уверен, иначе ниже
4. Слот app/name/query: извлеки самое короткое осмысленное значение
5. Не добавляй лишних полей, не пиши пояснений

Примеры:
"запусти мне телегу пожалуйста" → {{"intent":"open_app","slots":{{"app":"telegram"}},"confidence":0.9}}
"скинь окошко вниз" → {{"intent":"minimize_all","slots":{{}},"confidence":0.85}}
"что в буфере" → {{"intent":"clipboard_read","slots":{{}},"confidence":0.9}}
"закрой эту хрень" → {{"intent":"close_window","slots":{{}},"confidence":0.75}}
"расскажи анекдот" → {{"intent":"unknown","slots":{{}},"confidence":0.0}}
"""
