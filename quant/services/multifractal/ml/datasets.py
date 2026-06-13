"""Time-safe supervised datasets for multifractal ML baselines."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupervisedMultifractalRow:
    """One time-ordered feature row with horizon-aware targets.

    Example:
        `row = SupervisedMultifractalRow(0, 1, {"x": 1.0}, {"y": 0.0})`
    """

    source_index: int
    target_index: int
    features: dict[str, float]
    targets: dict[str, float | str]


@dataclass(frozen=True, slots=True)
class WalkForwardSplit:
    """One purged walk-forward split.

    Example:
        `split = WalkForwardSplit([0, 1], [3], 1)`
    """

    train_indices: list[int]
    test_indices: list[int]
    purge_gap: int


def build_supervised_dataset(
    feature_rows: Sequence[Mapping[str, float]],
    returns: Sequence[float],
    regimes: Sequence[str] | None = None,
    horizon: int = 1,
    var_threshold: float = 0.03,
) -> list[SupervisedMultifractalRow]:
    """Build horizon-aware supervised rows from ordered features.

    Example:
        `rows = build_supervised_dataset(features, returns, horizon=1)`
    """
    _positive_int(horizon, "horizon")
    count = min(len(feature_rows), len(returns)) - horizon
    return [
        _row_at(feature_rows, returns, regimes or (), index, horizon, var_threshold)
        for index in range(max(0, count))
    ]


def build_walk_forward_splits(
    row_count: int,
    train_size: int,
    test_size: int,
    purge_gap: int = 0,
) -> list[WalkForwardSplit]:
    """Build non-random walk-forward splits with optional purge gap."""
    _positive_int(train_size, "train_size")
    _positive_int(test_size, "test_size")
    if purge_gap < 0:
        raise ValueError(f"Invalid purge_gap {purge_gap!r}; expected >= 0")
    splits: list[WalkForwardSplit] = []
    start = 0
    while start + train_size + purge_gap + test_size <= row_count:
        splits.append(_split_at(start, train_size, test_size, purge_gap))
        start += test_size
    return splits


def dataset_matrix(
    rows: Sequence[SupervisedMultifractalRow],
) -> tuple[list[str], list[list[float]]]:
    """Return stable feature columns and matrix rows."""
    columns = sorted({key for row in rows for key in row.features})
    matrix = [[row.features.get(column, 0.0) for column in columns] for row in rows]
    return columns, matrix


def _row_at(
    feature_rows: Sequence[Mapping[str, float]],
    returns: Sequence[float],
    regimes: Sequence[str],
    index: int,
    horizon: int,
    var_threshold: float,
) -> SupervisedMultifractalRow:
    target = index + horizon
    return SupervisedMultifractalRow(
        source_index=index,
        target_index=target,
        features={key: float(value) for key, value in feature_rows[index].items()},
        targets=_targets(returns, regimes, target, var_threshold),
    )


def _targets(
    returns: Sequence[float],
    regimes: Sequence[str],
    target: int,
    var_threshold: float,
) -> dict[str, float | str]:
    value = float(returns[target])
    return {
        "next_return_sign": _sign(value),
        "next_volatility": abs(value),
        "next_drawdown_event": float(value <= -var_threshold),
        "next_regime": regimes[target] if target < len(regimes) else "unknown",
        "var_breach": float(-value > var_threshold),
    }


def _split_at(
    start: int,
    train_size: int,
    test_size: int,
    purge_gap: int,
) -> WalkForwardSplit:
    train_end = start + train_size
    test_start = train_end + purge_gap
    return WalkForwardSplit(
        train_indices=list(range(start, train_end)),
        test_indices=list(range(test_start, test_start + test_size)),
        purge_gap=purge_gap,
    )


def _sign(value: float) -> float:
    if value > 0.0:
        return 1.0
    if value < 0.0:
        return -1.0
    return 0.0


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")
