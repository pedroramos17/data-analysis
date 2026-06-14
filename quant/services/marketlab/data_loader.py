"""MarketLab local data loading helpers."""

from __future__ import annotations

from collections.abc import Iterable


def rows_from_values(values: Iterable[float]) -> list[dict[str, object]]:
    """Convert scalar values into timestamp-free local rows."""
    return [
        {"index": index, "value": float(value)}
        for index, value in enumerate(values)
    ]
