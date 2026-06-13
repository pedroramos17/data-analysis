"""Parquet export wrapper for finance prediction datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from sourceflow.warehouse.parquet_io import write_parquet_rows


def write_finance_parquet(
    rows: Sequence[Mapping[str, object]], path: str | Path
) -> Path:
    """Write rows to parquet using pyarrow when installed.

    Example:
        `write_finance_parquet(rows, "dataset.parquet")`
    """
    return write_parquet_rows(rows, path)
