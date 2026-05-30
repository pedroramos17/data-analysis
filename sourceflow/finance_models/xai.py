"""Explainability payloads for finance predictions."""

from __future__ import annotations


def finance_prediction_explanation(
    feature_attribution: dict[str, float],
    graph_paths: list[list[str]],
    factor_contribution: dict[str, float],
) -> dict[str, object]:
    """Return a diagnostics-only finance prediction explanation.

    Example:
        `payload = finance_prediction_explanation({}, [], {})`
    """
    return {
        "feature_attribution": feature_attribution,
        "graph_paths": graph_paths,
        "factor_contribution": factor_contribution,
        "boundary": "No truth claims; only signal evidence and model diagnostics.",
    }
