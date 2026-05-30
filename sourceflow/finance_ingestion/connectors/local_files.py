"""Local CSV, JSONL, and optional parquet finance imports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from sourceflow.config.feature_flags import require_feature


def read_local_financial_records(path: str | Path) -> list[dict[str, object]]:
    """Read a supported local market or fundamental dataset.

    Example:
        `records = read_local_financial_records("sample.csv")`
    """
    require_feature("FIN_DATA_CORE")
    file_path = Path(path)
    if file_path.suffix == ".csv":
        return _read_csv(file_path)
    if file_path.suffix == ".jsonl":
        return _read_jsonl(file_path)
    if file_path.suffix == ".parquet":
        return _read_parquet(file_path)
    raise ValueError(f"Invalid dataset path {file_path}; expected csv/jsonl/parquet")


def _read_csv(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


def _read_parquet(path: Path) -> list[dict[str, object]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError(
            "parquet import failed; expected pyarrow installed"
        ) from error
    return pq.read_table(path).to_pylist()
