"""Multifractal risk scoring for Quant research diagnostics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quant.services.multifractal.risk.var import expected_shortfall, historical_var


@dataclass(frozen=True, slots=True)
class MultifractalRiskAssessment:
    """Separated risk assessment for one asset or window.

    Example:
        `assessment = compute_asset_multifractal_risk(returns, features)`
    """

    forecast_risk: dict[str, float]
    portfolio_risk: dict[str, float]
    liquidity_risk: dict[str, float]
    model_risk: dict[str, float | str]
    regime_risk: dict[str, float]
    multifractal_risk: dict[str, float]
    risk_score: float

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable risk assessment.

        Example:
            `payload = assessment.to_json_dict()`
        """
        return {
            "forecast_risk": self.forecast_risk,
            "portfolio_risk": self.portfolio_risk,
            "liquidity_risk": self.liquidity_risk,
            "model_risk": self.model_risk,
            "regime_risk": self.regime_risk,
            "multifractal_risk": self.multifractal_risk,
            "risk_score": self.risk_score,
        }


def compute_asset_multifractal_risk(
    returns: Sequence[float],
    features: Mapping[str, float],
) -> MultifractalRiskAssessment:
    """Compute separated traditional and multifractal risk components.

    Example:
        `risk = compute_asset_multifractal_risk(returns, {"delta_alpha": 0.2})`
    """
    values = _finite_returns(returns)
    forecast = _forecast_risk(values)
    portfolio = _portfolio_risk(values)
    multifractal = _multifractal_components(features)
    score = _risk_score(forecast, portfolio, multifractal)
    return MultifractalRiskAssessment(
        forecast,
        portfolio,
        _liquidity_risk(features),
        _model_risk(features),
        _regime_risk(features),
        multifractal,
        score,
    )


def compute_rolling_multifractal_risk(
    symbol: str,
    returns: Sequence[float],
    features: Mapping[str, float],
    window_size: int,
    step: int,
) -> list[dict[str, object]]:
    """Compute no-lookahead rolling risk rows.

    Example:
        `rows = compute_rolling_multifractal_risk("SPY", returns, {}, 64, 16)`
    """
    _positive_int(window_size, "window_size")
    _positive_int(step, "step")
    values = _finite_returns(returns)
    rows: list[dict[str, object]] = []
    for start in range(0, len(values) - window_size + 1, step):
        end = start + window_size - 1
        assessment = compute_asset_multifractal_risk(values[start : end + 1], features)
        rows.append(_rolling_row(symbol, start, end, assessment))
    return rows


def _rolling_row(
    symbol: str,
    start: int,
    end: int,
    assessment: MultifractalRiskAssessment,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "window_start": start,
        "window_end": end,
        "risk_score": assessment.risk_score,
        "forecast_risk": assessment.forecast_risk,
        "multifractal_risk": assessment.multifractal_risk,
    }


def _forecast_risk(values: Sequence[float]) -> dict[str, float]:
    return {
        "realized_volatility": _volatility(values),
        "downside_volatility": _volatility([min(value, 0.0) for value in values]),
        "historical_var_95": historical_var(values, 0.95),
        "expected_shortfall_95": expected_shortfall(values, 0.95),
    }


def _portfolio_risk(values: Sequence[float]) -> dict[str, float]:
    return {
        "max_drawdown": _max_drawdown(values),
        "drawdown_duration": _duration(values),
    }


def _multifractal_components(features: Mapping[str, float]) -> dict[str, float]:
    return {
        "delta_alpha": float(features.get("delta_alpha", 0.0)),
        "spectrum_asymmetry": abs(float(features.get("spectrum_asymmetry", 0.0))),
        "intermittency": float(features.get("intermittency_proxy", 0.0)),
        "h_deviation": abs(float(features.get("hurst_h2", 0.5)) - 0.5),
        "scaling_instability": 1.0
        - float(features.get("scaling_quality_mean_r2", 1.0)),
        "extreme_sensitivity": float(features.get("extreme_sensitivity_score", 0.0)),
    }


def _liquidity_risk(features: Mapping[str, float]) -> dict[str, float]:
    return {"liquidity_proxy": float(features.get("liquidity_proxy", 0.0))}


def _model_risk(features: Mapping[str, float]) -> dict[str, float | str]:
    return {
        "confidence_penalty": float(features.get("finite_size_warning", 0.0)),
        "causality_claim": "none",
    }


def _regime_risk(features: Mapping[str, float]) -> dict[str, float]:
    return {
        "turbulent_regime_probability": float(
            features.get("turbulent_regime_probability", 0.0)
        )
    }


def _risk_score(
    forecast: Mapping[str, float],
    portfolio: Mapping[str, float],
    multifractal: Mapping[str, float],
) -> float:
    raw = forecast["realized_volatility"] * 10.0
    raw += forecast["expected_shortfall_95"] * 5.0
    raw += portfolio["max_drawdown"]
    raw += multifractal["delta_alpha"]
    raw += multifractal["intermittency"]
    raw += multifractal["extreme_sensitivity"]
    return max(0.0, raw)


def _finite_returns(returns: Sequence[float]) -> list[float]:
    if not returns:
        raise ValueError(f"Invalid returns {returns!r}; expected non-empty series")
    values = [float(value) for value in returns]
    for value in values:
        if math.isfinite(value):
            continue
        raise ValueError(f"Invalid return value {value!r}; expected finite float")
    return values


def _volatility(values: Sequence[float]) -> float:
    center = sum(values) / len(values)
    return math.sqrt(sum((value - center) ** 2 for value in values) / len(values))


def _max_drawdown(returns: Sequence[float]) -> float:
    wealth = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in returns:
        wealth *= 1.0 + value
        peak = max(peak, wealth)
        drawdown = max(drawdown, (peak - wealth) / peak)
    return drawdown


def _duration(returns: Sequence[float]) -> float:
    wealth = 1.0
    peak = 1.0
    current = 0
    longest = 0
    for value in returns:
        wealth *= 1.0 + value
        if wealth >= peak:
            peak = wealth
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return float(longest)


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")
