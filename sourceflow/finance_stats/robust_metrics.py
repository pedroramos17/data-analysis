"""Robust performance metric helpers."""

from __future__ import annotations

from math import sqrt


def sharpe_ratio(returns: list[float]) -> float:
    """Return a simple Sharpe ratio.

    Example:
        `sharpe_ratio([0.01, -0.01])`
    """
    return _mean(returns) / (_std(returns) or 1e-12)


def sortino_ratio(returns: list[float]) -> float:
    """Return a downside-deviation Sortino ratio.

    Example:
        `sortino_ratio([0.01, -0.02])`
    """
    downside = [min(value, 0.0) for value in returns]
    return _mean(returns) / (_std(downside) or 1e-12)


def calmar_ratio(total_return: float, max_drawdown: float) -> float:
    """Return total return divided by maximum drawdown.

    Example:
        `calmar_ratio(0.2, 0.1) == 2`
    """
    return total_return / (max_drawdown or 1e-12)


def _mean(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def _std(values: list[float]) -> float:
    mean_value = _mean(values)
    return sqrt(
        sum((value - mean_value) ** 2 for value in values) / max(len(values), 1)
    )
