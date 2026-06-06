"""Source abstractions and local file helpers for ingestion."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceAsset:
    """Asset descriptor discovered by an ingestion source."""

    symbol: str
    asset_type: str = "equity"
    timeframe: str = "1d"


@dataclass(frozen=True, slots=True)
class RawIngestionBatch:
    """Raw source rows for one discovered asset."""

    asset: SourceAsset
    rows: Sequence[Mapping[str, object]]


class IngestionSource(Protocol):
    """Provider-neutral ingestion source boundary.

    Example:
        `source.fetch_raw_data(source.discover_assets()[0])`
    """

    name: str
    schema_type: str

    def discover_assets(self) -> list[SourceAsset]:
        """Return assets available to ingest."""

    def fetch_raw_data(self, asset: SourceAsset) -> RawIngestionBatch:
        """Fetch raw rows for an asset without writing storage."""


def configured_rows(config: Mapping[str, object]) -> list[dict[str, object]]:
    """Return inline or local-file rows from an ingestion config."""
    rows = config.get("rows")
    if isinstance(rows, Sequence) and not isinstance(rows, str | bytes):
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    input_path = str(config.get("input_path") or config.get("path") or "")
    if input_path:
        return read_local_rows(Path(input_path))
    return []


def configured_symbols(
    config: Mapping[str, object],
    rows: Sequence[Mapping[str, object]],
) -> list[str]:
    """Return configured symbols or derive them from rows."""
    symbols = config.get("symbols")
    if isinstance(symbols, Sequence) and not isinstance(symbols, str | bytes):
        values = [str(symbol).upper() for symbol in symbols if str(symbol).strip()]
        if values:
            return values
    symbol = str(config.get("symbol") or "").strip()
    if symbol:
        return [symbol.upper()]
    derived = sorted({str(row.get("symbol") or "").upper() for row in rows})
    return [symbol for symbol in derived if symbol] or ["SPY"]


def rows_for_symbol(
    rows: Sequence[Mapping[str, object]],
    symbol: str,
) -> list[dict[str, object]]:
    """Filter local rows for one symbol, preserving rows without a symbol field."""
    selected: list[dict[str, object]] = []
    for row in rows:
        row_symbol = str(row.get("symbol") or symbol).upper()
        if row_symbol == symbol.upper():
            selected.append(dict(row) | {"symbol": symbol.upper()})
    return selected


def read_local_rows(path: Path) -> list[dict[str, object]]:
    """Read CSV, JSON, JSONL, Parquet, or fallback-ingestion rows from disk."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(path)
    if suffix == ".json":
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            return [dict(row) for row in loaded if isinstance(row, Mapping)]
        if isinstance(loaded, Mapping) and isinstance(loaded.get("rows"), list):
            return [dict(row) for row in loaded["rows"] if isinstance(row, Mapping)]
    if suffix in {".jsonl", ".ndjson"}:
        return [
            dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if suffix == ".parquet":
        return _read_parquet_or_fallback(path)
    raise ValueError(f"Unsupported ingestion input path {path}; expected CSV/JSON/JSONL/Parquet")


def _read_csv(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_parquet_or_fallback(path: Path) -> list[dict[str, object]]:
    data = path.read_bytes()
    if data.startswith(b"INGESTION_FALLBACK_JSONL\n"):
        return [
            dict(json.loads(line))
            for line in data.decode("utf-8").splitlines()[1:]
            if line.strip()
        ]
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow is required to read Parquet ingestion input") from exc
    return [dict(row) for row in pq.read_table(path).to_pylist()]
