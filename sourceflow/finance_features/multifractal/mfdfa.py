"""Lightweight MF-DFA and Hurst approximations."""

from __future__ import annotations

from math import log, sqrt

Number = float | int


def generalized_hurst_exponent(series: list[Number], q: float = 2.0) -> float:
    """Estimate generalized Hurst exponent from lagged q-moments.

    Example:
        `h = generalized_hurst_exponent([1, 2, 4, 8], q=2)`
    """
    values = [float(value) for value in series]
    if len(values) < 4:
        return 0.5
    points = _lag_moment_points(values, q)
    return _bounded_slope(points)


def mfdfa(series: list[Number], q_grid: list[float] | None = None) -> dict[str, object]:
    """Return a compact MF-DFA baseline feature dictionary.

    Example:
        `features = mfdfa([1, 2, 3, 4])`
    """
    q_values = q_grid or [-2.0, 0.0, 2.0]
    hurst = {str(_clean_q(q)): generalized_hurst_exponent(series, q) for q in q_values}
    tau = {key: float(key) * value - 1.0 for key, value in hurst.items()}
    alpha = list(hurst.values())
    return {
        "q_grid_json": q_values,
        "hurst_json": hurst,
        "tau_json": tau,
        "alpha_json": alpha,
    }


def mfdma(series: list[Number], window: int = 3) -> dict[str, float]:
    """Return a simple moving-average detrended fluctuation proxy.

    Example:
        `result = mfdma([1, 2, 1, 3])`
    """
    values = [float(value) for value in series]
    residuals = _moving_residuals(values, window)
    fluctuation = sqrt(sum(value * value for value in residuals) / len(residuals))
    return {"window": float(window), "fluctuation": fluctuation}


def _lag_moment_points(values: list[float], q: float) -> list[tuple[float, float]]:
    max_lag = min(5, len(values) - 1)
    return [_lag_moment(values, lag, q) for lag in range(1, max_lag + 1)]


def _lag_moment(values: list[float], lag: int, q: float) -> tuple[float, float]:
    diffs = [
        abs(values[index] - values[index - lag]) for index in range(lag, len(values))
    ]
    moment = _moment(diffs, q)
    return log(float(lag)), log(max(moment, 1e-12))


def _moment(values: list[float], q: float) -> float:
    if q == 0:
        return sum(log(max(value, 1e-12)) for value in values) / len(values)
    return sum(value ** abs(q) for value in values) / len(values)


def _bounded_slope(points: list[tuple[float, float]]) -> float:
    slope = _slope(points) / 2.0
    return max(0.0, min(1.5, slope if slope > 0 else 0.5))


def _slope(points: list[tuple[float, float]]) -> float:
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in points)
    denominator = sum((x - mean_x) ** 2 for x, _y in points) or 1e-12
    return numerator / denominator


def _moving_residuals(values: list[float], window: int) -> list[float]:
    width = max(1, window)
    return [
        value - _mean(values[max(0, index - width + 1) : index + 1])
        for index, value in enumerate(values)
    ]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _clean_q(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value
