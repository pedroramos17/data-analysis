"""Objective helpers for multifractal portfolio allocation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def inverse_variance_scores(
    symbols: Sequence[str],
    covariance: Sequence[Sequence[float]],
) -> dict[str, float]:
    """Return inverse diagonal covariance scores.

    Example:
        `scores = inverse_variance_scores(["A"], [[0.01]])`
    """
    return {
        symbol: _inverse_positive(_variance_at(covariance, index))
        for index, symbol in enumerate(symbols)
    }


def multifractal_penalty(
    features: Mapping[str, float],
    regime_label: str = "",
) -> float:
    """Return a positive penalty multiplier from risk and regime features."""
    score = float(features.get("delta_alpha", 0.0))
    score += float(features.get("intermittency_proxy", 0.0))
    score += abs(float(features.get("spectrum_asymmetry", 0.0)))
    score += _regime_penalty(regime_label)
    return 1.0 / (1.0 + max(0.0, score))


def risk_contribution(
    weights: Mapping[str, float],
    covariance: Sequence[Sequence[float]],
) -> dict[str, float]:
    """Return diagonal covariance risk contribution by symbol."""
    symbols = list(weights)
    raw = {
        symbol: weights[symbol] * weights[symbol] * _variance_at(covariance, index)
        for index, symbol in enumerate(symbols)
    }
    total = sum(raw.values()) or 1.0
    return {symbol: value / total for symbol, value in raw.items()}


def multifractal_risk_contribution(
    weights: Mapping[str, float],
    risk_features: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """Return normalized multifractal contribution by symbol."""
    raw = {
        symbol: abs(weight) * _feature_score(risk_features.get(symbol, {}))
        for symbol, weight in weights.items()
    }
    total = sum(raw.values()) or 1.0
    return {symbol: value / total for symbol, value in raw.items()}


def _feature_score(features: Mapping[str, float]) -> float:
    return 1.0 + float(features.get("delta_alpha", 0.0)) + float(
        features.get("intermittency_proxy", 0.0)
    )


def _regime_penalty(regime_label: str) -> float:
    if "crash" in regime_label or "liquidity" in regime_label:
        return 2.0
    if "turbulent" in regime_label:
        return 1.0
    return 0.0


def _variance_at(covariance: Sequence[Sequence[float]], index: int) -> float:
    if index >= len(covariance) or index >= len(covariance[index]):
        return 0.0
    return max(float(covariance[index][index]), 0.0)


def _inverse_positive(value: float) -> float:
    return 0.0 if value <= 0.0 else 1.0 / value
