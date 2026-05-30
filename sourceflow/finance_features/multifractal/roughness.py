"""Roughness and intermittency proxies."""

from __future__ import annotations

from math import log

from sourceflow.finance_features.multifractal.mfdfa import generalized_hurst_exponent

Number = float | int


def rolling_hurst(series: list[Number], window: int = 8) -> list[float]:
    """Return rolling Hurst approximations.

    Example:
        `values = rolling_hurst([1, 2, 3, 4], 3)`
    """
    if len(series) < window:
        return [generalized_hurst_exponent(series)]
    return [
        generalized_hurst_exponent(series[index - window : index])
        for index in range(window, len(series) + 1)
    ]


def variation_ratio(prices: list[Number]) -> float:
    """Return path variation divided by endpoint displacement.

    Example:
        `variation_ratio([1, 2, 1])`
    """
    return _variation([float(value) for value in prices])


def path_roughness(prices: list[Number], epsilon: float = 1e-12) -> float:
    """Return log-price path roughness with epsilon protection.

    Example:
        `path_roughness([100, 101, 99])`
    """
    log_prices = [log(float(value)) for value in prices]
    numerator = sum(
        abs(right - left)
        for left, right in zip(log_prices, log_prices[1:], strict=False)
    )
    denominator = abs(log_prices[-1] - log_prices[0]) + epsilon
    return numerator / denominator


def spectrum_width(alpha_values: list[Number]) -> float:
    """Return multifractal spectrum width.

    Example:
        `spectrum_width([0.2, 0.7])`
    """
    values = [float(value) for value in alpha_values]
    return max(values) - min(values) if values else 0.0


def intermittency_proxy(hurst_json: dict[str, float]) -> float:
    """Return Hurst spread as an intermittency proxy.

    Example:
        `intermittency_proxy({"-2": 0.3, "2": 0.8})`
    """
    values = list(hurst_json.values())
    return max(values) - min(values) if values else 0.0


def _variation(values: list[float]) -> float:
    numerator = sum(
        abs(right - left) for left, right in zip(values, values[1:], strict=False)
    )
    denominator = abs(values[-1] - values[0]) + 1e-12
    return numerator / denominator
