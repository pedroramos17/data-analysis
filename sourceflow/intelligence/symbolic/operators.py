"""Vectorized symbolic operators for dataframe execution."""

from __future__ import annotations

import math
from collections.abc import Callable

import pandas as pd

SeriesOperator = Callable[..., pd.Series]


def operator_functions() -> dict[str, SeriesOperator]:
    """Return executable dataframe operator functions.

    Example:
        `functions = operator_functions()`
    """
    return {
        "add": _add,
        "sub": _sub,
        "mul": _mul,
        "div": _div,
        "div_safe": _div,
        "max": _max,
        "min": _min,
        "clip": _clip,
        "abs": _abs,
        "neg": _neg,
        "log1p": _log1p,
        "sqrt": _sqrt,
        "sigmoid": _sigmoid,
        "rank": _rank,
        "percentile": _rank,
        "zscore": _zscore,
        "zscore_by_event": _zscore,
        "winsorize": _winsorize,
        "smooth": _smooth,
        "entropy": _entropy,
        "frame_entropy": _entropy,
        "stance_entropy": _entropy,
        "gini": _gini,
        "js_divergence": _js_divergence,
        "kl_divergence": _kl_divergence,
        "cosine_sim": _cosine_sim,
        "jaccard": _jaccard,
        "coverage_ratio": _coverage_ratio,
        "set_count": _set_count,
        "graph_degree": _graph_value,
        "graph_pagerank": _graph_value,
        "graph_betweenness": _graph_value,
        "graph_neighbor_mean": _graph_value,
        "graph_neighbor_sum": _graph_value,
        "graph_path_count": _graph_value,
        "graph_bridge_score": _graph_value,
        "graph_community_count": _graph_value,
    }


def _add(left: pd.Series, right: pd.Series) -> pd.Series:
    return left.fillna(0) + right.fillna(0)


def _sub(left: pd.Series, right: pd.Series) -> pd.Series:
    return left.fillna(0) - right.fillna(0)


def _mul(left: pd.Series, right: pd.Series) -> pd.Series:
    return left.fillna(0) * right.fillna(0)


def _div(left: pd.Series, right: pd.Series) -> pd.Series:
    divisor = right.replace(0, 1).fillna(1)
    return left.fillna(0) / divisor


def _max(left: pd.Series, right: pd.Series) -> pd.Series:
    return pd.concat([left, right], axis=1).max(axis=1)


def _min(left: pd.Series, right: pd.Series) -> pd.Series:
    return pd.concat([left, right], axis=1).min(axis=1)


def _clip(value: pd.Series) -> pd.Series:
    return value.clip(lower=-5, upper=5)


def _abs(value: pd.Series) -> pd.Series:
    return value.abs()


def _neg(value: pd.Series) -> pd.Series:
    return -value.fillna(0)


def _log1p(value: pd.Series) -> pd.Series:
    return value.clip(lower=0).map(math.log1p)


def _sqrt(value: pd.Series) -> pd.Series:
    return value.clip(lower=0).map(math.sqrt)


def _sigmoid(value: pd.Series) -> pd.Series:
    return value.fillna(0).map(lambda item: 1 / (1 + math.exp(-float(item))))


def _rank(value: pd.Series) -> pd.Series:
    return value.rank(pct=True).fillna(0)


def _zscore(value: pd.Series) -> pd.Series:
    std = float(value.std() or 0)
    if std == 0:
        return value * 0
    return (value - float(value.mean())) / std


def _winsorize(value: pd.Series) -> pd.Series:
    lower = float(value.quantile(0.05))
    upper = float(value.quantile(0.95))
    return value.clip(lower=lower, upper=upper)


def _smooth(value: pd.Series) -> pd.Series:
    return value.fillna(0).rolling(window=3, min_periods=1).mean()


def _set_count(value: pd.Series) -> pd.Series:
    return value.map(_count_set_like)


def _entropy(value: pd.Series) -> pd.Series:
    return value.map(lambda item: _entropy_value(_distribution(item)))


def _gini(value: pd.Series) -> pd.Series:
    return value.map(
        lambda item: 1.0 - sum(weight**2 for weight in _distribution(item))
    )


def _js_divergence(left: pd.Series, right: pd.Series) -> pd.Series:
    return _distribution_pair(left, right, _js_value)


def _kl_divergence(left: pd.Series, right: pd.Series) -> pd.Series:
    return _distribution_pair(left, right, _kl_value)


def _cosine_sim(left: pd.Series, right: pd.Series) -> pd.Series:
    return _distribution_pair(left, right, _cosine_value)


def _jaccard(left: pd.Series, right: pd.Series) -> pd.Series:
    return _set_pair(left, right, _jaccard_value)


def _coverage_ratio(left: pd.Series, right: pd.Series) -> pd.Series:
    return _set_pair(left, right, _coverage_ratio_value)


def _graph_value(value: pd.Series) -> pd.Series:
    return value.map(lambda item: 1.0 if item else 0.0)


def _count_set_like(value: object) -> int:
    if isinstance(value, list | tuple | set):
        return len(value)
    return 1 if value else 0


def _distribution_pair(
    left: pd.Series,
    right: pd.Series,
    function: Callable[[list[float], list[float]], float],
) -> pd.Series:
    aligned = pd.concat([left, right], axis=1)
    return aligned.apply(
        lambda row: function(*_distribution_vectors(row.iloc[0], row.iloc[1])),
        axis=1,
    )


def _set_pair(
    left: pd.Series,
    right: pd.Series,
    function: Callable[[set[str], set[str]], float],
) -> pd.Series:
    aligned = pd.concat([left, right], axis=1)
    return aligned.apply(
        lambda row: function(_set_value(row.iloc[0]), _set_value(row.iloc[1])), axis=1
    )


def _distribution(value: object) -> list[float]:
    if isinstance(value, dict):
        raw_values = list(value.values())
    elif isinstance(value, list | tuple):
        raw_values = list(value)
    else:
        raw_values = [_float_item(value)]
    weights = [max(0.0, _float_item(item)) for item in raw_values]
    total = sum(weights)
    if total <= 0:
        return [0.0 for _item in weights] or [0.0]
    return [item / total for item in weights]


def _distribution_vectors(
    left: object,
    right: object,
) -> tuple[list[float], list[float]]:
    if isinstance(left, dict) or isinstance(right, dict):
        return _dict_distribution_vectors(left, right)
    return _distribution(left), _distribution(right)


def _dict_distribution_vectors(
    left: object,
    right: object,
) -> tuple[list[float], list[float]]:
    left_mapping = left if isinstance(left, dict) else {}
    right_mapping = right if isinstance(right, dict) else {}
    left_keys = {str(key) for key in left_mapping}
    right_keys = {str(key) for key in right_mapping}
    keys = sorted(left_keys | right_keys)
    left_weights = [_float_item(left_mapping.get(key, 0)) for key in keys]
    right_weights = [_float_item(right_mapping.get(key, 0)) for key in keys]
    return _normalize_weights(left_weights), _normalize_weights(right_weights)


def _normalize_weights(weights: list[float]) -> list[float]:
    positive_weights = [max(0.0, item) for item in weights]
    total = sum(positive_weights)
    if total <= 0:
        return [0.0 for _item in positive_weights] or [0.0]
    return [item / total for item in positive_weights]


def _set_value(value: object) -> set[str]:
    if isinstance(value, set):
        return {str(item) for item in value}
    if isinstance(value, list | tuple):
        return {str(item) for item in value}
    return {str(value)} if value else set()


def _entropy_value(weights: list[float]) -> float:
    return float(-sum(weight * math.log(weight, 2) for weight in weights if weight > 0))


def _js_value(left: list[float], right: list[float]) -> float:
    left, right = _same_length(left, right)
    midpoint = [
        (left_item + right_item) / 2
        for left_item, right_item in zip(left, right, strict=True)
    ]
    return (_kl_value(left, midpoint) + _kl_value(right, midpoint)) / 2


def _kl_value(left: list[float], right: list[float]) -> float:
    left, right = _same_length(left, right)
    total = 0.0
    for left_item, right_item in zip(left, right, strict=True):
        if left_item > 0 and right_item > 0:
            total += left_item * math.log(left_item / right_item, 2)
    return float(total)


def _cosine_value(left: list[float], right: list[float]) -> float:
    left, right = _same_length(left, right)
    numerator = sum(
        left_item * right_item
        for left_item, right_item in zip(left, right, strict=True)
    )
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(numerator / (left_norm * right_norm))


def _jaccard_value(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _coverage_ratio_value(left: set[str], right: set[str]) -> float:
    if not right:
        return 0.0
    return len(left & right) / len(right)


def _same_length(
    left: list[float], right: list[float]
) -> tuple[list[float], list[float]]:
    size = max(len(left), len(right), 1)
    return left + [0.0] * (size - len(left)), right + [0.0] * (size - len(right))


def _float_item(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
