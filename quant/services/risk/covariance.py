"""Volatility and covariance risk models."""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import mean, pstdev


def historical_volatility(returns: Sequence[float]) -> float:
    """Return population historical volatility for local returns.

    Example:
        `historical_volatility([0.01, -0.02])`
    """
    if len(returns) < 2:
        return 0.0
    return pstdev(float(value) for value in returns)


def ewma_volatility(returns: Sequence[float], decay: float = 0.94) -> float:
    """Return EWMA volatility using past returns only.

    Example:
        `ewma_volatility([0.01, -0.02])`
    """
    variance = 0.0
    for value in returns:
        variance = decay * variance + (1 - decay) * float(value) ** 2
    return math.sqrt(variance)


def covariance_shrinkage(series: Sequence[Sequence[float]]) -> list[list[float]]:
    """Return a diagonal-shrunk covariance matrix.

    Example:
        `covariance_shrinkage([[0.01, -0.02], [0.02, 0.01]])`
    """
    matrix = _covariance_matrix(series)
    return _shrink_to_diagonal(matrix, shrinkage=0.2)


def pca_risk_model(series: Sequence[Sequence[float]]) -> dict[str, object]:
    """Return a dependency-free PCA risk proxy from covariance diagonal.

    Example:
        `pca_risk_model([[0.01], [0.02]])`
    """
    matrix = covariance_shrinkage(series)
    variances = [row[index] for index, row in enumerate(matrix)]
    total = sum(variances)
    ratios = [_safe_ratio(value, total) for value in variances]
    return {"method": "diagonal_pca_proxy", "explained_variance_ratio": ratios}


def _covariance_matrix(series: Sequence[Sequence[float]]) -> list[list[float]]:
    rows = [[float(value) for value in row] for row in series]
    return [[_covariance(left, right) for right in rows] for left in rows]


def _covariance(left: Sequence[float], right: Sequence[float]) -> float:
    length = min(len(left), len(right))
    if length < 2:
        return 0.0
    left_mean = mean(left[:length])
    right_mean = mean(right[:length])
    covariance = sum(
        (left[i] - left_mean) * (right[i] - right_mean) for i in range(length)
    )
    return covariance / length


def _shrink_to_diagonal(
    matrix: Sequence[Sequence[float]],
    shrinkage: float,
) -> list[list[float]]:
    shrunk: list[list[float]] = []
    for row_index, row in enumerate(matrix):
        shrunk.append(_shrunk_row(row_index, row, shrinkage))
    return shrunk


def _shrunk_row(
    row_index: int,
    row: Sequence[float],
    shrinkage: float,
) -> list[float]:
    return [
        _shrunk_value(row_index, col_index, value, shrinkage)
        for col_index, value in enumerate(row)
    ]


def _shrunk_value(
    row_index: int,
    col_index: int,
    value: float,
    shrinkage: float,
) -> float:
    if row_index == col_index:
        return value
    return value * (1 - shrinkage)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator
