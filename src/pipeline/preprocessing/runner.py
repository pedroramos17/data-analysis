"""Deterministic preprocessing runner."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from glob import glob
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.pipeline.ingestion.source_base import read_local_rows
from src.pipeline.ingestion.validators import rows_to_parquet_bytes
from src.pipeline.preprocessing.aligner import align_calendar, remove_duplicates, sort_rows
from src.pipeline.preprocessing.cleaner import clean_rows
from src.pipeline.preprocessing.corporate_actions import (
    apply_corporate_actions,
    load_corporate_actions,
)
from src.pipeline.preprocessing.missing_values import impute_missing_bars, mark_missing_ohlcv
from src.pipeline.preprocessing.normalizer import normalize_output_rows, normalize_quality_report
from src.pipeline.preprocessing.outliers import detect_outliers, quality_report
from src.providers.registry import ProviderRegistry, build_provider_registry
from src.storage.manifest import content_hash


@dataclass(frozen=True, slots=True)
class PreprocessingResult:
    """Preprocessing output metadata."""

    status: str
    input_rows: int
    bronze_rows: int
    silver_rows: int
    duplicates_removed: int
    bronze_path: str
    silver_path: str
    quality_report_path: str
    quality_report: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable result."""
        return {
            "status": self.status,
            "input_rows": self.input_rows,
            "bronze_rows": self.bronze_rows,
            "silver_rows": self.silver_rows,
            "duplicates_removed": self.duplicates_removed,
            "bronze_path": self.bronze_path,
            "silver_path": self.silver_path,
            "quality_report_path": self.quality_report_path,
            "quality_report": self.quality_report,
        }


def run_preprocessing(
    config: Mapping[str, object],
    registry: ProviderRegistry | None = None,
) -> PreprocessingResult:
    """Run deterministic raw-to-bronze/silver preprocessing."""
    active_registry = registry or build_provider_registry(load_runtime_settings())
    lake_root = _config_path(config, "lake_root", active_registry.settings.storage.local_root)
    raw_path = _config_path(config, "raw_path", lake_root / "raw")
    raw_rows, reader = read_raw_parquet_rows(raw_path, require_duckdb=_bool(config.get("require_duckdb"), False))
    cleaned = clean_rows(raw_rows)
    cleaned = mark_missing_ohlcv(cleaned)
    sorted_rows = sort_rows(cleaned)
    deduped, duplicates_removed = remove_duplicates(sorted_rows)
    bronze_rows = normalize_output_rows(deduped)

    imputed = impute_missing_bars(deduped)
    aligned, calendar_report = align_calendar(
        imputed,
        frequency=str(config.get("calendar_frequency") or config.get("frequency") or "1d"),
        explicit_calendar=_string_list(config.get("calendar", [])),
    )
    actions = load_corporate_actions(config)
    adjusted, corporate_report = apply_corporate_actions(
        aligned,
        actions,
        as_of=str(config.get("corporate_actions_as_of") or "2999-12-31T00:00:00+00:00"),
    )
    flagged = detect_outliers(
        adjusted,
        price_jump_threshold=float(config.get("price_jump_threshold") or 0.2),
        stale_periods=int(config.get("stale_periods") or 2),
    )
    silver_rows = normalize_output_rows(flagged)

    bronze_path = str(config.get("bronze_path") or "bronze/market_bars/part-000.parquet")
    silver_path = str(config.get("silver_path") or "silver/market_bars/part-000.parquet")
    quality_path = str(config.get("quality_report_path") or "silver/market_bars/_quality_report.json")
    bronze_bytes = rows_to_parquet_bytes(bronze_rows)
    silver_bytes = rows_to_parquet_bytes(silver_rows)
    storage = active_registry.get_storage()
    bronze_uri = storage.put_bytes(bronze_path, bronze_bytes, "application/vnd.apache.parquet")
    silver_uri = storage.put_bytes(silver_path, silver_bytes, "application/vnd.apache.parquet")
    report = _build_report(
        config,
        raw_path,
        reader,
        raw_rows,
        bronze_rows,
        silver_rows,
        duplicates_removed,
        calendar_report,
        corporate_report,
        bronze_path,
        bronze_uri,
        bronze_bytes,
        silver_path,
        silver_uri,
        silver_bytes,
    )
    report_bytes = json.dumps(report, sort_keys=True, indent=2, default=str).encode("utf-8")
    storage.put_bytes(quality_path, report_bytes, "application/json")
    return PreprocessingResult(
        status="COMPLETED",
        input_rows=len(raw_rows),
        bronze_rows=len(bronze_rows),
        silver_rows=len(silver_rows),
        duplicates_removed=duplicates_removed,
        bronze_path=bronze_path,
        silver_path=silver_path,
        quality_report_path=quality_path,
        quality_report=report,
    )


def read_raw_parquet_rows(
    raw_path: str | Path,
    *,
    require_duckdb: bool = False,
) -> tuple[list[dict[str, object]], str]:
    """Read raw Parquet files through DuckDB, with local fallback for mock files."""
    files = _raw_parquet_files(raw_path)
    try:
        return _read_with_duckdb(files), "duckdb"
    except Exception as exc:
        if require_duckdb:
            raise RuntimeError("DuckDB raw Parquet read failed") from exc
        return _read_with_local_fallback(files), "local_fallback"


def _read_with_duckdb(files: Sequence[Path]) -> list[dict[str, object]]:
    import duckdb

    relation = _duckdb_relation(files)
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("set timezone='UTC'")
        result = connection.execute(f"select * from {relation}")
        columns = [column[0] for column in result.description or []]
        return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]
    finally:
        connection.close()


def _read_with_local_fallback(files: Sequence[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in files:
        partitions = _partitions_from_path(path)
        for row in read_local_rows(path):
            rows.append(partitions | dict(row))
    return rows


def _build_report(
    config: Mapping[str, object],
    raw_path: Path,
    reader: str,
    raw_rows: Sequence[Mapping[str, object]],
    bronze_rows: Sequence[Mapping[str, object]],
    silver_rows: Sequence[Mapping[str, object]],
    duplicates_removed: int,
    calendar_report: Mapping[str, object],
    corporate_report: Mapping[str, object],
    bronze_path: str,
    bronze_uri: str,
    bronze_bytes: bytes,
    silver_path: str,
    silver_uri: str,
    silver_bytes: bytes,
) -> dict[str, object]:
    base = quality_report(silver_rows)
    report = {
        "status": "COMPLETED",
        "reader": reader,
        "raw_path": str(raw_path),
        "input_rows": len(raw_rows),
        "bronze_rows": len(bronze_rows),
        "silver_rows": len(silver_rows),
        "duplicates_removed": duplicates_removed,
        "timestamp_alignment": {
            "timezone": "UTC",
            "policy": "all timestamps normalized to explicit UTC ISO-8601 strings",
            "calendar": dict(calendar_report),
        },
        "missing_value_policy": "previous_observation_only_no_future_leakage",
        "no_future_leakage": True,
        "corporate_actions": dict(corporate_report),
        "quality": base,
        "outputs": {
            "bronze": {
                "path": bronze_path,
                "uri": bronze_uri,
                "content_hash": content_hash(bronze_bytes),
            },
            "silver": {
                "path": silver_path,
                "uri": silver_uri,
                "content_hash": content_hash(silver_bytes),
            },
        },
        "config": {
            "calendar_frequency": str(config.get("calendar_frequency") or config.get("frequency") or "1d"),
            "price_jump_threshold": float(config.get("price_jump_threshold") or 0.2),
            "stale_periods": int(config.get("stale_periods") or 2),
        },
    }
    return normalize_quality_report(report)


def _raw_parquet_files(raw_path: str | Path) -> list[Path]:
    path = Path(raw_path)
    if path.is_file() and path.suffix == ".parquet":
        return [path]
    if path.is_dir():
        files = sorted(Path(match) for match in glob(str(path / "**" / "*.parquet"), recursive=True))
        if files:
            return files
    raise FileNotFoundError(f"No raw Parquet files found at {path}")


def _duckdb_relation(files: Sequence[Path]) -> str:
    values = ", ".join("'" + path.as_posix().replace("'", "''") + "'" for path in files)
    return f"read_parquet([{values}], hive_partitioning=true, union_by_name=true)"


def _partitions_from_path(path: Path) -> dict[str, object]:
    partitions: dict[str, object] = {}
    for part in path.parts:
        if "=" in part:
            key, value = part.split("=", 1)
            partitions[key] = value
    return partitions


def _config_path(config: Mapping[str, object], key: str, default: Path) -> Path:
    value = config.get(key)
    if value in (None, ""):
        return default
    return Path(str(value))


def _string_list(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise ValueError(f"Invalid list value {value!r}; expected list or comma string")


def _bool(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}
