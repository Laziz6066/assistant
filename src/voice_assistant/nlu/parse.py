from __future__ import annotations
import json
from loguru import logger

from voice_assistant.core.types import Intent


def parse_and_validate(content: str, catalog: dict[str, dict],
                       min_confidence: float) -> Intent:
    """Parse an ollama JSON response and validate it against the catalog.

    Returns Intent.unknown() on ANY problem: bad JSON, missing keys, intent
    not in catalog, low confidence, slot type mismatch, missing required slot.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        logger.debug(f"LLM returned non-JSON: {content!r}")
        return Intent.unknown()

    if not isinstance(data, dict):
        logger.debug(f"LLM response not a dict: {content!r}")
        return Intent.unknown()

    intent_name = data.get("intent")
    if not isinstance(intent_name, str):
        logger.debug(f"LLM missing/invalid intent field: {content!r}")
        return Intent.unknown()

    if intent_name == "unknown":
        return Intent.unknown()

    if intent_name not in catalog:
        logger.debug(f"LLM hallucinated intent {intent_name!r}, "
                      f"not in catalog")
        return Intent.unknown()

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        logger.debug(f"LLM invalid confidence: {content!r}")
        return Intent.unknown()

    if confidence < min_confidence:
        return Intent.unknown()

    slots_raw = data.get("slots", {})
    if not isinstance(slots_raw, dict):
        logger.debug(f"LLM slots is not a dict: {content!r}")
        return Intent.unknown()

    declared_slots = catalog[intent_name]["slots"]
    coerced: dict[str, int | str] = {}
    for slot_name, slot_type in declared_slots:
        if slot_name not in slots_raw:
            logger.debug(f"LLM missing required slot {slot_name!r} "
                          f"for intent {intent_name!r}")
            return Intent.unknown()
        raw_val = slots_raw[slot_name]
        if not isinstance(raw_val, (str, int, float, bool)):
            logger.debug(f"LLM slot {slot_name!r} has non-primitive value "
                          f"of type {type(raw_val).__name__}: {raw_val!r}")
            return Intent.unknown()
        if slot_type == "int":
            try:
                coerced[slot_name] = int(raw_val)
            except (TypeError, ValueError):
                logger.debug(f"LLM uncoercible int slot {slot_name!r}: "
                              f"{raw_val!r}")
                return Intent.unknown()
        else:
            coerced[slot_name] = str(raw_val).strip()

    return Intent(name=intent_name, slots=coerced, confidence=confidence)
