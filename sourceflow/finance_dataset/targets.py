"""Target builders for finance prediction datasets."""

from __future__ import annotations


def forward_return_horizon(prices: list[float], horizon: int) -> list[float | None]:
    """Return forward simple returns for a fixed horizon.

    Example:
        `targets = forward_return_horizon([100, 101], 1)`
    """
    return [_forward_return(prices, index, horizon) for index in range(len(prices))]


def direction_horizon(prices: list[float], horizon: int) -> list[int | None]:
    """Return positive-forward-return direction labels.

    Example:
        `labels = direction_horizon([100, 101], 1)`
    """
    values = forward_return_horizon(prices, horizon)
    return [None if value is None else int(value > 0) for value in values]


def volatility_horizon(returns: list[float], horizon: int) -> list[float | None]:
    """Return forward realized volatility labels.

    Example:
        `vols = volatility_horizon([.01, -.01], 2)`
    """
    return [
        _window_volatility(returns[index : index + horizon])
        for index in range(len(returns))
    ]


def _forward_return(prices: list[float], index: int, horizon: int) -> float | None:
    target_index = index + horizon
    if target_index >= len(prices) or prices[index] == 0:
        return None
    return prices[target_index] / prices[index] - 1.0


def _window_volatility(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(value * value for value in values) ** 0.5
