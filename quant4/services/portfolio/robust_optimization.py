"""Robust optimization fallbacks for Quant4 portfolios."""

from __future__ import annotations

from collections.abc import Mapping


def shrink_expected_returns(
    expected_returns: Mapping[str, float],
    shrinkage: float = 0.5,
) -> dict[str, float]:
    """Shrink expected returns toward the cross-sectional mean.

    Example:
        `shrink_expected_returns({"AAA": 0.10, "BBB": 0.00})`
    """
    if not expected_returns:
        return {}
    bounded = min(1.0, max(0.0, float(shrinkage)))
    center = sum(float(value) for value in expected_returns.values())
    center = center / len(expected_returns)
    return {
        symbol: (1.0 - bounded) * float(value) + bounded * center
        for symbol, value in expected_returns.items()
    }


def add_covariance_diagonal_buffer(
    covariance: list[list[float]],
    buffer: float = 1e-6,
) -> list[list[float]]:
    """Return covariance with a diagonal robustness buffer.

    Example:
        `add_covariance_diagonal_buffer([[0.1]])`
    """
    return [
        [
            _buffered_value(row_index, col_index, value, buffer)
            for col_index, value in enumerate(row)
        ]
        for row_index, row in enumerate(covariance)
    ]


def _buffered_value(
    row_index: int,
    col_index: int,
    value: float,
    buffer: float,
) -> float:
    return float(value) + float(buffer) if row_index == col_index else float(value)
