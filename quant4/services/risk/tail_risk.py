"""Tail and drawdown risk models."""

from __future__ import annotations

from collections.abc import Sequence


def historical_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Return historical VaR as a positive loss number.

    Example:
        `historical_var([0.01, -0.03])`
    """
    losses = sorted(-float(value) for value in returns)
    if not losses:
        return 0.0
    index = max(0, int(len(losses) * confidence) - 1)
    return losses[min(index, len(losses) - 1)]


def expected_shortfall(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Return CVaR / Expected Shortfall as a positive loss number.

    Example:
        `expected_shortfall([0.01, -0.03])`
    """
    var_value = historical_var(returns, confidence)
    tail_losses = [-float(value) for value in returns if -float(value) >= var_value]
    if not tail_losses:
        return var_value
    return sum(tail_losses) / len(tail_losses)


def max_drawdown(prices: Sequence[float]) -> float:
    """Return max drawdown as a negative ratio.

    Example:
        `max_drawdown([100.0, 90.0])`
    """
    peak = prices[0] if prices else 0.0
    worst = 0.0
    for price in prices:
        peak = max(peak, float(price))
        worst = min(worst, _safe_ratio(float(price) - peak, peak))
    return worst


def drawdown_duration(prices: Sequence[float]) -> int:
    """Return the longest period spent below prior high.

    Example:
        `drawdown_duration([100.0, 90.0, 95.0])`
    """
    peak = prices[0] if prices else 0.0
    current = 0
    longest = 0
    for price in prices:
        peak, current = _duration_step(peak, current, float(price))
        longest = max(longest, current)
    return longest


def _duration_step(peak: float, current: int, price: float) -> tuple[float, int]:
    if price >= peak:
        return price, 0
    return peak, current + 1


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
