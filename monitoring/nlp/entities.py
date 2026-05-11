"""Entity extraction through spaCy with a deterministic fallback."""

from __future__ import annotations

import re

ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3}\b")


def extract_entities(
    text: str, model_name: str = "en_core_web_sm"
) -> dict[str, object]:
    """Extract named entities with spaCy when the model is local.

    Example:
        `extract_entities("OpenAI met Reuters in London.")`
    """
    spacy_result = _extract_with_spacy(text, model_name)
    if not spacy_result["error"]:
        return spacy_result
    fallback_items = _regex_entities(text)
    spacy_result["items"] = fallback_items
    spacy_result["backend"] = "regex-fallback"
    return spacy_result


def _extract_with_spacy(text: str, model_name: str) -> dict[str, object]:
    try:
        import spacy
    except ImportError as error:
        return _entity_error("spacy", model_name, error)
    try:
        document = spacy.load(model_name)(text)
    except OSError as error:
        return _entity_error("spacy-model", model_name, error)
    items = [{"text": entity.text, "label": entity.label_} for entity in document.ents]
    return {"backend": f"spacy:{model_name}", "items": items, "error": ""}


def _regex_entities(text: str) -> list[dict[str, object]]:
    seen: dict[str, dict[str, object]] = {}
    for match in ENTITY_PATTERN.finditer(text):
        value = match.group(0).strip()
        if len(value) > 2:
            seen.setdefault(value, {"text": value, "label": "UNKNOWN"})
    return list(seen.values())[:24]


def _entity_error(
    backend: str,
    model_name: str,
    error: Exception,
) -> dict[str, object]:
    message = f"{backend} unavailable for entities; expected local model {model_name}: {error}"
    return {"backend": f"{backend}-unavailable", "items": [], "error": message}
