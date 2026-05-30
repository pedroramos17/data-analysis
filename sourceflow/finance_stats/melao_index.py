"""Melao-index-inspired model evaluation metrics."""

from __future__ import annotations

from math import log, sqrt

from sourceflow.config.feature_flags import require_feature

Number = float | int


def equity_log_regression_score(equity_curve: list[Number]) -> float:
    """Return log-equity trend score adjusted by path fit.

    Example:
        `score = equity_log_regression_score([100, 101, 102])`
    """
    require_feature("FIN_STATS_MELAO_INDEX")
    logs = [log(max(float(value), 1e-12)) for value in equity_curve]
    slope, r_squared = _slope_and_r2(logs)
    return slope * r_squared


def max_drawdown(equity_curve: list[Number]) -> float:
    """Return maximum drawdown as a positive fraction.

    Example:
        `max_drawdown([100, 90, 110]) == 0.1`
    """
    peak = float(equity_curve[0])
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, float(value))
        worst = max(worst, (peak - float(value)) / max(peak, 1e-12))
    return worst


def expected_drawdown(equity_curve: list[Number]) -> float:
    """Return mean drawdown over the equity path.

    Example:
        `expected_drawdown([100, 90, 110])`
    """
    peak = float(equity_curve[0])
    drawdowns: list[float] = []
    for value in equity_curve:
        peak = max(peak, float(value))
        drawdowns.append((peak - float(value)) / max(peak, 1e-12))
    return sum(drawdowns) / len(drawdowns)


def melao_inspired_score(equity_curve: list[Number]) -> float:
    """Return a drawdown- and time-normalized profitability score.

    Example:
        `score = melao_inspired_score([100, 101, 102])`
    """
    require_feature("FIN_STATS_MELAO_INDEX")
    trend = equity_log_regression_score(equity_curve)
    penalty = 1.0 + max_drawdown(equity_curve) + expected_drawdown(equity_curve)
    penalty += _underwater_duration_ratio(equity_curve)
    return trend / penalty


def compare_performance_metrics(equity_curve: list[Number]) -> dict[str, float]:
    """Return standard and Melao-inspired performance metrics.

    Example:
        `metrics = compare_performance_metrics([100, 101, 99])`
    """
    returns = _simple_returns(equity_curve)
    return {
        "sharpe": _mean(returns) / (_std(returns) or 1e-12),
        "sortino": _sortino(returns),
        "calmar": _calmar(equity_curve),
        "melao_inspired": melao_inspired_score(equity_curve),
        "max_drawdown": max_drawdown(equity_curve),
        "expected_drawdown": expected_drawdown(equity_curve),
    }


def _slope_and_r2(values: list[float]) -> tuple[float, float]:
    x_values = [float(index) for index in range(len(values))]
    slope = _slope(x_values, values)
    intercept = _mean(values) - slope * _mean(x_values)
    fitted = [intercept + slope * x for x in x_values]
    return slope, _r_squared(values, fitted)


def _slope(x_values: list[float], y_values: list[float]) -> float:
    mean_x = _mean(x_values)
    mean_y = _mean(y_values)
    denominator = sum((x - mean_x) ** 2 for x in x_values) or 1e-12
    return (
        sum(
            (x - mean_x) * (y - mean_y)
            for x, y in zip(x_values, y_values, strict=False)
        )
        / denominator
    )


def _r_squared(values: list[float], fitted: list[float]) -> float:
    mean_y = _mean(values)
    total = sum((value - mean_y) ** 2 for value in values) or 1e-12
    residual = sum(
        (value - fit) ** 2 for value, fit in zip(values, fitted, strict=False)
    )
    return max(0.0, 1.0 - residual / total)


def _underwater_duration_ratio(equity_curve: list[Number]) -> float:
    peak = float(equity_curve[0])
    underwater = 0
    for value in equity_curve:
        peak = max(peak, float(value))
        underwater += int(float(value) < peak)
    return underwater / max(len(equity_curve), 1)


def _simple_returns(equity_curve: list[Number]) -> list[float]:
    return [
        (float(right) - float(left)) / float(left)
        for left, right in zip(equity_curve, equity_curve[1:], strict=False)
    ]


def _sortino(returns: list[float]) -> float:
    downside = [min(value, 0.0) for value in returns]
    return _mean(returns) / (_std(downside) or 1e-12)


def _calmar(equity_curve: list[Number]) -> float:
    growth = float(equity_curve[-1]) / float(equity_curve[0]) - 1.0
    return growth / (max_drawdown(equity_curve) or 1e-12)


def _mean(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def _std(values: list[float]) -> float:
    mean_value = _mean(values)
    return sqrt(
        sum((value - mean_value) ** 2 for value in values) / max(len(values), 1)
    )
