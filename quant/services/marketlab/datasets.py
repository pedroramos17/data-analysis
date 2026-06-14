"""MarketLab dataset helpers."""

from __future__ import annotations

from collections.abc import Sequence


def build_train_only_synthetic_rows(
    rows: Sequence[Sequence[float]],
    generator_name: str,
) -> list[dict[str, object]]:
    """Return synthetic rows explicitly restricted to train split."""
    return [
        _synthetic_row(row, generator_name, index)
        for index, row in enumerate(rows)
    ]


def _synthetic_row(
    row: Sequence[float],
    generator_name: str,
    index: int,
) -> dict[str, object]:
    return {
        "row_index": index,
        "values": [float(value) for value in row],
        "generator": generator_name,
        "split": "train",
        "eligible_for_validation": False,
        "eligible_for_test": False,
    }
