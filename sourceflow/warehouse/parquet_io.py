"""Parquet I/O helpers owned by the warehouse boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path


def write_parquet_rows(
    rows: Sequence[Mapping[str, object]], path: str | Path
) -> Path:
    """Write row mappings to parquet using pyarrow when installed."""

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError(
            "parquet export failed; expected pyarrow installed"
        ) from error
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(list(rows)), output_path)
    return output_path
