"""Polynomial detrending helpers shared by multifractal methods."""

from __future__ import annotations

from collections.abc import Sequence


def detrended_residuals(values: Sequence[float], order: int) -> list[float]:
    """Return residuals after polynomial detrending.

    Example:
        `residuals = detrended_residuals([1.0, 2.0, 1.5], order=1)`
    """
    coefficients = polynomial_fit(values, order)
    return [
        value - evaluate_polynomial(coefficients, float(index))
        for index, value in enumerate(values)
    ]


def detrended_variance(values: Sequence[float], order: int) -> float:
    """Return mean squared residual after polynomial detrending.

    Example:
        `variance = detrended_variance([1.0, 2.0, 1.5], order=1)`
    """
    residuals = detrended_residuals(values, order)
    return sum(residual * residual for residual in residuals) / len(residuals)


def polynomial_fit(values: Sequence[float], order: int) -> list[float]:
    """Fit a polynomial trend using normal equations.

    Example:
        `coefficients = polynomial_fit([1.0, 2.0, 3.0], order=1)`
    """
    size = order + 1
    matrix = [
        [_power_sum(len(values), row + col) for col in range(size)]
        for row in range(size)
    ]
    rhs = [
        sum(value * (float(index) ** row) for index, value in enumerate(values))
        for row in range(size)
    ]
    return solve_linear_system(matrix, rhs)


def evaluate_polynomial(coefficients: Sequence[float], x_value: float) -> float:
    """Evaluate polynomial coefficients at one x value.

    Example:
        `value = evaluate_polynomial([1.0, 2.0], 3.0)`
    """
    return sum(
        coefficient * (x_value**power)
        for power, coefficient in enumerate(coefficients)
    )


def solve_linear_system(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a small dense linear system by Gauss-Jordan elimination.

    Example:
        `solution = solve_linear_system([[1.0]], [2.0])`
    """
    augmented = [row[:] + [rhs[index]] for index, row in enumerate(matrix)]
    for pivot_index in range(len(rhs)):
        _pivot_rows(augmented, pivot_index)
        _normalize_pivot_row(augmented, pivot_index)
        _eliminate_column(augmented, pivot_index)
    return [row[-1] for row in augmented]


def _power_sum(length: int, power: int) -> float:
    return sum(float(index) ** power for index in range(length))


def _pivot_rows(matrix: list[list[float]], pivot_index: int) -> None:
    best = max(
        range(pivot_index, len(matrix)),
        key=lambda row: abs(matrix[row][pivot_index]),
    )
    if abs(matrix[best][pivot_index]) < 1e-12:
        raise ValueError("Invalid polynomial fit matrix; expected full-rank system")
    matrix[pivot_index], matrix[best] = matrix[best], matrix[pivot_index]


def _normalize_pivot_row(matrix: list[list[float]], pivot_index: int) -> None:
    pivot = matrix[pivot_index][pivot_index]
    matrix[pivot_index] = [value / pivot for value in matrix[pivot_index]]


def _eliminate_column(matrix: list[list[float]], pivot_index: int) -> None:
    for row_index, row in enumerate(matrix):
        if row_index == pivot_index:
            continue
        factor = row[pivot_index]
        matrix[row_index] = [
            value - factor * matrix[pivot_index][index]
            for index, value in enumerate(row)
        ]
