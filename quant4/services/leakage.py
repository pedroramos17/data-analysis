"""Leakage checks for Quant4 feature and label timelines."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime


def assert_no_future_feature_timestamps(
    rows: Iterable[Mapping[str, object]],
    feature_key: str = "feature_timestamp",
    label_key: str = "label_timestamp",
) -> None:
    """Reject rows where features occur after their labels.

    Example:
        `assert_no_future_feature_timestamps(rows)`
    """
    for index, row in enumerate(rows):
        feature_time = _timestamp(row, feature_key, index)
        label_time = _timestamp(row, label_key, index)
        _reject_future_feature(index, feature_time, label_time)


def _timestamp(row: Mapping[str, object], key: str, index: int) -> datetime:
    value = row.get(key)
    if isinstance(value, datetime):
        return value
    raise ValueError(
        f"Invalid row {index} {key} {value!r}; expected datetime timestamp"
    )


def _reject_future_feature(
    index: int,
    feature_time: datetime,
    label_time: datetime,
) -> None:
    if feature_time <= label_time:
        return
    raise ValueError(
        f"Invalid row {index} feature_timestamp {feature_time.isoformat()}; "
        f"expected <= label_timestamp {label_time.isoformat()}"
    )
