"""Return and volatility helpers for finance features."""

from __future__ import annotations

from math import log, sqrt

Number = float | int


def log_return(previous_price: Number, current_price: Number) -> float:
    """Return the log return between two positive prices.

    Example:
        `log_return(100, 101)`
    """
    previous = _positive(previous_price, "previous_price")
    current = _positive(current_price, "current_price")
    return log(current / previous)


def log_returns(prices: list[Number]) -> list[float]:
    """Return sequential log returns for positive prices.

    Example:
        `returns = log_returns([100, 101, 102])`
    """
    return [
        log_return(left, right) for left, right in zip(prices, prices[1:], strict=False)
    ]


def realized_volatility(prices: list[Number]) -> float:
    """Return root-mean-square realized volatility from log returns.

    Example:
        `realized_volatility([100, 101, 99])`
    """
    returns = log_returns(prices)
    if not returns:
        return 0.0
    return sqrt(sum(value * value for value in returns) / len(returns))


def _positive(value: Number, label: str) -> float:
    parsed = float(value)
    if parsed > 0:
        return parsed
    raise ValueError(f"Invalid {label}={value!r}; expected positive number")
