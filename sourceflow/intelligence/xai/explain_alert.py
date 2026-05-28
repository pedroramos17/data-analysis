"""Score decomposition helpers for alerts."""

from __future__ import annotations


def explain_alert_score(score_parts: dict[str, float]) -> str:
    """Explain alert score components without truth judgments.

    Example:
        `text = explain_alert_score({"coverage": 0.7})`
    """
    parts = [f"{name}={value:.2f}" for name, value in sorted(score_parts.items())]
    return "Score reflects comparison and propagation signals: " + ", ".join(parts)
