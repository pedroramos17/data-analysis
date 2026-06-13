"""Stress scenario helpers for multifractal risk diagnostics."""

from __future__ import annotations

from collections.abc import Mapping

SCENARIO_SHOCKS = {
    "2008": -0.18,
    "COVID": -0.22,
    "rate_shock": -0.08,
    "commodity_shock": -0.10,
    "FX_devaluation": -0.12,
    "correlation_breakdown": -0.09,
    "liquidity_freeze": -0.15,
    "futures_roll_shock": -0.06,
}


def apply_stress_scenarios(base_score: float) -> dict[str, float]:
    """Apply deterministic stress scenarios to a base risk score.

    Example:
        `outputs = apply_stress_scenarios(1.0)`
    """
    return {
        name: base_score * (1.0 + abs(shock))
        for name, shock in SCENARIO_SHOCKS.items()
    }


def scenario_summary(outputs: Mapping[str, float]) -> dict[str, float]:
    """Return compact stress scenario summary metrics.

    Example:
        `summary = scenario_summary(outputs)`
    """
    values = list(outputs.values())
    return {
        "max_stress_score": max(values),
        "mean_stress_score": sum(values) / len(values),
    }
