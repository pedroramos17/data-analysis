"""Claim normalization helpers."""

from __future__ import annotations

import re

NEGATIVE_TERMS = frozenset(
    {
        "anomaly",
        "cut",
        "delay",
        "disruption",
        "downgrade",
        "fraud",
        "investigation",
        "lawsuit",
        "lower",
        "probe",
        "recall",
        "sanction",
        "shock",
        "shortfall",
        "warning",
    }
)
POSITIVE_TERMS = frozenset(
    {
        "beats",
        "growth",
        "higher",
        "launch",
        "raises",
        "upgrade",
    }
)
MODALITY_BY_PREDICATE = {
    "alleges": "alleged",
    "alleged": "alleged",
    "denies": "denied",
    "denied": "denied",
    "forecasts": "forecasted",
    "forecast": "forecasted",
    "expects": "forecasted",
    "signals": "forecasted",
    "rumors": "rumored",
    "rumoured": "rumored",
    "confirms": "confirmed",
    "confirmed": "confirmed",
}


def normalize_predicate(value: str) -> str:
    """Return a compact snake-case predicate."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "unknown"


def normalize_object_literal(value: str) -> str:
    """Normalize object literal whitespace and trailing punctuation."""
    return " ".join(value.strip().strip(".;:!? ").split())


def infer_modality(predicate: str, evidence_text: str = "") -> str:
    """Infer claim modality from predicate and evidence text."""
    normalized = normalize_predicate(predicate)
    if normalized in MODALITY_BY_PREDICATE:
        return MODALITY_BY_PREDICATE[normalized]
    lowered = evidence_text.lower()
    if "rumor" in lowered or "rumour" in lowered:
        return "rumored"
    if "alleg" in lowered:
        return "alleged"
    return "asserted"


def infer_polarity(predicate: str, object_text: str, evidence_text: str = "") -> str:
    """Infer coarse polarity from claim text."""
    tokens = set(re.findall(r"[a-z0-9_]+", f"{predicate} {object_text} {evidence_text}".lower()))
    if tokens & NEGATIVE_TERMS:
        return "negative"
    if tokens & POSITIVE_TERMS:
        return "positive"
    return "neutral"


def infer_tense(evidence_text: str) -> str:
    """Infer a minimal tense label."""
    lowered = evidence_text.lower()
    if any(token in lowered for token in (" will ", " expects ", " forecast", " signals ")):
        return "future"
    if any(token in lowered for token in (" was ", " were ", " reported ", " faced ")):
        return "past"
    return "present"
