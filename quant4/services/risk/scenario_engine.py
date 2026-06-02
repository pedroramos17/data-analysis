"""Named stress scenario engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

STRESS_SCENARIOS: dict[str, dict[str, object]] = {
    "2008": {"shock": -0.35, "risk_type": "portfolio_risk"},
    "COVID": {"shock": -0.25, "risk_type": "forecast_risk"},
    "rate shock": {"shock": -0.12, "risk_type": "model_risk"},
    "commodity shock": {"shock": -0.18, "risk_type": "portfolio_risk"},
    "FX devaluation": {"shock": -0.20, "risk_type": "portfolio_risk"},
    "correlation breakdown": {"shock": -0.15, "risk_type": "model_risk"},
    "liquidity freeze": {"shock": -0.22, "risk_type": "liquidity_risk"},
    "futures roll shock": {"shock": -0.10, "risk_type": "portfolio_risk"},
}


def run_scenarios(
    returns: Sequence[float],
    scenarios: Sequence[str] | None = None,
) -> dict[str, dict[str, object]]:
    """Return deterministic outputs for named stress scenarios.

    Example:
        `run_scenarios([0.01], ["2008"])`
    """
    names = list(scenarios or STRESS_SCENARIOS)
    return {name: scenario_output(name, returns) for name in names}


def scenario_output(name: str, returns: Sequence[float]) -> dict[str, object]:
    """Return one scenario result without account or advice claims.

    Example:
        `scenario_output("2008", [0.01])`
    """
    config = _scenario_config(name)
    baseline = sum(float(value) for value in returns)
    shock = float(config["shock"])
    return {
        "shock": shock,
        "stressed_return": baseline + shock,
        "risk_type": config["risk_type"],
        "claim_scope": "research_risk_only",
    }


def _scenario_config(name: str) -> Mapping[str, object]:
    if name in STRESS_SCENARIOS:
        return STRESS_SCENARIOS[name]
    expected = sorted(STRESS_SCENARIOS)
    raise ValueError(f"Invalid stress scenario {name!r}; expected one of {expected}")
