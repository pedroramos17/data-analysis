"""Leakage-safe time-series windows for multifractal preprocessing."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quant4.services.multifractal.preprocessing._series import _positive_int


@dataclass(frozen=True, slots=True)
class TimeSeriesWindow:
    """Single horizon-aware training window.

    Example:
        `window = sliding_windows([1.0, 2.0, 3.0], 2)[0]`
    """

    train_indices: list[int]
    train_values: tuple[object, ...]
    label_index: int
    label_value: object
    window_start: int
    window_end: int
    label_timestamp: int
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    """Anchored walk-forward training and validation split.

    Example:
        `split = anchored_walk_forward_windows([1, 2, 3], 2, 1)[0]`
    """

    train_indices: list[int]
    validation_indices: list[int]
    label_index: int
    window_start: int
    window_end: int
    validation_start: int
    validation_end: int
    label_timestamp: int
    metadata: dict[str, object]


def sliding_windows(
    values: Sequence[object],
    window_size: int,
    horizon: int = 1,
) -> list[TimeSeriesWindow]:
    """Build fixed-length windows with labels strictly after the training span.

    Example:
        `windows = sliding_windows([1.0, 2.0, 3.0], 2, horizon=1)`
    """
    _validate_series_length(values, window_size + horizon, "sliding_windows")
    last_start = len(values) - window_size - horizon + 1
    return [
        _build_time_series_window(values, start, window_size, horizon, "sliding")
        for start in range(last_start)
    ]


def expanding_windows(
    values: Sequence[object],
    min_train_size: int,
    horizon: int = 1,
) -> list[TimeSeriesWindow]:
    """Build expanding windows anchored at the first observation.

    Example:
        `windows = expanding_windows([1.0, 2.0, 3.0], 2)`
    """
    _validate_series_length(values, min_train_size + horizon, "expanding_windows")
    max_train_size = len(values) - horizon + 1
    return [
        _build_time_series_window(values, 0, train_size, horizon, "expanding")
        for train_size in range(min_train_size, max_train_size)
    ]


def anchored_walk_forward_windows(
    values: Sequence[object],
    train_size: int,
    validation_size: int,
    horizon: int = 1,
) -> list[WalkForwardWindow]:
    """Build anchored walk-forward splits with validation after training.

    Example:
        `splits = anchored_walk_forward_windows([1, 2, 3, 4], 2, 1)`
    """
    _validate_walk_forward_request(values, train_size, validation_size, horizon)
    last_validation_start = len(values) - validation_size + 1
    return [
        _build_walk_forward_window(values, start, validation_size, horizon)
        for start in range(train_size, last_validation_start)
    ]


def _build_time_series_window(
    values: Sequence[object],
    start: int,
    window_size: int,
    horizon: int,
    method: str,
) -> TimeSeriesWindow:
    train_indices = list(range(start, start + window_size))
    label_index = start + window_size + horizon - 1
    return TimeSeriesWindow(
        train_indices,
        tuple(values[index] for index in train_indices),
        label_index,
        values[label_index],
        train_indices[0],
        train_indices[-1],
        label_index,
        {"method": method, "horizon": horizon},
    )


def _build_walk_forward_window(
    values: Sequence[object],
    validation_start: int,
    validation_size: int,
    horizon: int,
) -> WalkForwardWindow:
    validation_indices = list(
        range(validation_start, validation_start + validation_size)
    )
    label_index = validation_start + horizon - 1
    return WalkForwardWindow(
        list(range(0, validation_start)),
        validation_indices,
        label_index,
        0,
        validation_start - 1,
        validation_start,
        validation_indices[-1],
        label_index,
        {"method": "anchored_walk_forward", "horizon": horizon},
    )


def _validate_series_length(values: Sequence[object], minimum: int, label: str) -> None:
    _positive_int(minimum, "minimum")
    if len(values) >= minimum:
        return
    raise ValueError(
        f"Invalid {label} length {len(values)!r}; expected at least {minimum}"
    )


def _validate_walk_forward_request(
    values: Sequence[object],
    train_size: int,
    validation_size: int,
    horizon: int,
) -> None:
    _positive_int(train_size, "train_size")
    _positive_int(validation_size, "validation_size")
    _positive_int(horizon, "horizon")
    if horizon <= validation_size:
        _validate_series_length(values, train_size + validation_size, "walk_forward")
        return
    raise ValueError(f"Invalid horizon {horizon!r}; expected <= validation_size")
