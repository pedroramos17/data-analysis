"""Shared regime feature-row builders for multifractal smoke workflows."""

from __future__ import annotations

from collections.abc import Sequence


def build_regime_feature_rows(series: Sequence[float]) -> list[dict[str, float]]:
    """Build simple leakage-safe regime feature rows from ordered returns.

    Example:
        `rows = build_regime_feature_rows([0.01, -0.02])`
    """
    return [_regime_feature_row(float(value)) for value in series]


def _regime_feature_row(value: float) -> dict[str, float]:
    return {
        "hurst_h2": 0.5,
        "delta_alpha": abs(value),
        "spectrum_asymmetry": value,
        "tau_nonlinearity": abs(value),
        "realized_volatility": abs(value),
        "drawdown": min(0.0, value),
    }
