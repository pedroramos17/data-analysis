"""Lenient Quant 4.0 extraction schema parsing."""

from __future__ import annotations

import json
import re

from researchspace.services.status import normalize_support_status


def parse_quant_extraction_payload(raw_text: str) -> dict[str, object]:
    """Parse full or partial extraction JSON into a stable shape.

    Example:
        `parse_quant_extraction_payload('{"methodology": ["walk-forward"]}')`
    """
    parsed = _parse_full_object(raw_text)
    if parsed is None:
        parsed = _parse_partial_payload(raw_text)
    return {
        "methodology": _string_list(parsed.get("methodology")),
        "datasets": _string_list(parsed.get("datasets")),
        "models": _string_list(parsed.get("models")),
        "validation": _string_list(parsed.get("validation")),
        "factors": _factor_list(parsed.get("factors")),
        "support_status": normalize_support_status(parsed.get("support_status")),
        "raw_text": raw_text,
    }


def extraction_prompt_preview(title: str, context: str) -> str:
    """Build the local prompt for structured methodology extraction.

    Example:
        `extraction_prompt_preview("Paper", "chunk text")`
    """
    return (
        "Extract Quant 4.0 methodology as JSON with methodology, datasets, "
        f"models, validation, factors, and support_status.\nPaper: {title}\n{context}"
    )


def _parse_full_object(raw_text: str) -> dict[str, object] | None:
    candidate = _json_substring(raw_text)
    if not candidate:
        return None
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _parse_partial_payload(raw_text: str) -> dict[str, object]:
    return {
        "methodology": _partial_string_array(raw_text, "methodology"),
        "datasets": _partial_string_array(raw_text, "datasets"),
        "models": _partial_string_array(raw_text, "models"),
        "validation": _partial_string_array(raw_text, "validation"),
        "factors": [],
        "support_status": "NEEDS_REVIEW",
    }


def _json_substring(raw_text: str) -> str:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end <= start:
        return ""
    return raw_text[start : end + 1]


def _partial_string_array(raw_text: str, key: str) -> list[str]:
    pattern = rf'"{re.escape(key)}"\s*:\s*\[(?P<body>[^\]]*)'
    match = re.search(pattern, raw_text)
    if match is None:
        return []
    return re.findall(r'"([^"]+)"', match.group("body"))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _factor_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
