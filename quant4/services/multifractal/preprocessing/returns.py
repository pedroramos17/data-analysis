"""Return transforms for Quant4 multifractal preprocessing."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from quant4.services.multifractal.preprocessing._series import (
    _coerce_finite_series,
    _coerce_positive_series,
    _population_std,
    _positive_float,
    _positive_int,
)

VOLATILITY_MODES = ("daily", "intraday")


@dataclass(frozen=True, slots=True)
class ReturnTransform:
    """Adjacent price return transform used before multifractal analysis.

    Example:
        `record = compute_return_series([100.0, 101.0])[0]`
    """

    index: int
    previous_price: float
    current_price: float
    log_return: float
    simple_return: float
    abs_return: float
    squared_return: float


def compute_log_return(previous_price: float, current_price: float) -> float:
    """Compute the log return between two positive prices.

    Example:
        `value = compute_log_return(100.0, 101.0)`
    """
    previous = _positive_float(float(previous_price), "previous_price")
    current = _positive_float(float(current_price), "current_price")
    return math.log(current / previous)


def compute_simple_return(previous_price: float, current_price: float) -> float:
    """Compute the simple return between two positive prices.

    Example:
        `value = compute_simple_return(100.0, 101.0)`
    """
    previous = _positive_float(float(previous_price), "previous_price")
    current = _positive_float(float(current_price), "current_price")
    return (current / previous) - 1.0


def compute_return_series(prices: Sequence[float]) -> list[ReturnTransform]:
    """Compute adjacent no-lookahead return transforms from positive prices.

    Example:
        `returns = compute_return_series([100.0, 101.0, 102.0])`
    """
    validated = _coerce_positive_series(prices, "prices")
    return [
        _build_return_transform(index, previous, current)
        for index, (previous, current) in enumerate(
            zip(validated, validated[1:], strict=False),
            start=1,
        )
    ]


def rolling_realized_volatility(
    returns: Sequence[float],
    window: int,
    mode: str = "daily",
) -> list[float | None]:
    """Estimate rolling realized volatility without looking ahead.

    Example:
        `vol = rolling_realized_volatility([0.01, -0.02], 2, "intraday")`
    """
    validated = _coerce_finite_series(returns, "returns")
    _positive_int(window, "window")
    _validate_volatility_mode(mode)
    return [
        _rolling_volatility_at_index(validated, index, window, mode)
        for index in range(len(validated))
    ]


def absolute_and_squared_returns(
    log_returns: Sequence[float],
) -> list[tuple[float, float]]:
    """Return absolute and squared transforms for log-return inputs.

    Example:
        `features = absolute_and_squared_returns([0.01, -0.02])`
    """
    values = _coerce_finite_series(log_returns, "log_returns")
    return [(abs(value), value * value) for value in values]


def _build_return_transform(
    index: int,
    previous_price: float,
    current_price: float,
) -> ReturnTransform:
    log_value = compute_log_return(previous_price, current_price)
    simple_value = compute_simple_return(previous_price, current_price)
    return ReturnTransform(
        index,
        previous_price,
        current_price,
        log_value,
        simple_value,
        abs(log_value),
        log_value * log_value,
    )


def _rolling_volatility_at_index(
    returns: Sequence[float],
    index: int,
    window: int,
    mode: str,
) -> float | None:
    if index + 1 < window:
        return None
    window_values = returns[index - window + 1 : index + 1]
    if mode == "intraday":
        return math.sqrt(sum(value * value for value in window_values))
    return _population_std(window_values)


def _validate_volatility_mode(mode: str) -> None:
    if mode in VOLATILITY_MODES:
        return
    raise ValueError(
        f"Invalid volatility mode {mode!r}; expected one of {VOLATILITY_MODES}"
    )
