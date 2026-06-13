"""Risk attribution and model-risk metadata."""

from __future__ import annotations

from collections.abc import Mapping


def build_model_risk_fields(model_name: str) -> dict[str, object]:
    """Return model-risk fields without causality claims.

    Example:
        `build_model_risk_fields("pca_risk")`
    """
    return {
        "model_name": model_name,
        "causality_claim": False,
        "claim_scope": "associational_research_risk",
        "limitations": ["local sample sensitivity", "no live-system validation"],
    }


def build_risk_sections(
    forecast_risk: Mapping[str, object],
    portfolio_risk: Mapping[str, object],
    liquidity_risk: Mapping[str, object],
    model_risk: Mapping[str, object],
    regime_risk: Mapping[str, object],
) -> dict[str, object]:
    """Return separated risk report sections.

    Example:
        `build_risk_sections({}, {}, {}, {}, {})`
    """
    return {
        "forecast_risk": dict(forecast_risk),
        "portfolio_risk": dict(portfolio_risk),
        "liquidity_risk": dict(liquidity_risk),
        "model_risk": dict(model_risk),
        "regime_risk": dict(regime_risk),
    }
