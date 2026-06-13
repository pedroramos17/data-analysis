"""Dataset builder: reads features, applies window splits, writes train/val/test Parquet."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.pipeline.features.base import read_feature_input_rows
from src.pipeline.ingestion.validators import rows_to_parquet_bytes
from src.pipeline.windows.diagnostics import diagnose_window
from src.pipeline.windows.splitter import WindowSpec, split_windows
from src.providers.registry import ProviderRegistry
from src.storage.manifest import content_hash


@dataclass(frozen=True, slots=True)
class DatasetWindowOutput:
    """Output paths for one window."""

    window_id: int
    train_path: str
    validation_path: str
    test_path: str
    metadata_path: str
    train_rows: int
    validation_rows: int
    test_rows: int
    content_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "window_id": self.window_id,
            "train_path": self.train_path,
            "validation_path": self.validation_path,
            "test_path": self.test_path,
            "metadata_path": self.metadata_path,
            "train_rows": self.train_rows,
            "validation_rows": self.validation_rows,
            "test_rows": self.test_rows,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class DatasetBuildResult:
    """Top-level dataset build result."""

    status: str
    dataset_name: str
    version: str
    mode: str
    windows: int
    outputs: list[DatasetWindowOutput]
    diagnostics: list[dict[str, object]]
    overall_leakage_passed: bool
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "dataset_name": self.dataset_name,
            "version": self.version,
            "mode": self.mode,
            "windows": self.windows,
            "outputs": [o.to_dict() for o in self.outputs],
            "diagnostics": list(self.diagnostics),
            "overall_leakage_passed": self.overall_leakage_passed,
            "metadata": dict(self.metadata),
        }


def build_dataset(
    config: Mapping[str, object],
    registry: ProviderRegistry,
) -> DatasetBuildResult:
    """Build versioned sliding-window datasets from feature Parquet inputs."""
    dataset_name = str(config.get("dataset_name") or "default_dataset")
    version = str(config.get("version") or "phase6_v1")
    lake_root = _config_path(config, "lake_root", registry.settings.storage.local_root)
    input_path = _input_path(config, lake_root)
    output_root = _config_path(config, "output_root", lake_root / "datasets")

    # Read rows
    raw_rows, reader, input_uri = read_feature_input_rows(
        input_path,
        require_duckdb=_bool(config.get("require_duckdb"), False),
    )
    rows = _normalize_rows(raw_rows)

    # Generate window specs. CLI configs may group split policy under
    # `sliding_window`, while tests and direct callers often pass it flat.
    window_config = _window_config(config)
    windows = split_windows(rows, window_config)
    if not windows:
        return DatasetBuildResult(
            status="NO_WINDOWS",
            dataset_name=dataset_name,
            version=version,
            mode=str(window_config.get("mode") or "rolling"),
            windows=0,
            outputs=[],
            diagnostics=[],
            overall_leakage_passed=True,
            metadata={"input_uri": input_uri, "reader": reader, "input_rows": len(rows)},
        )

    # Build each window
    storage = registry.get_storage()
    outputs: list[DatasetWindowOutput] = []
    diagnostics: list[dict[str, object]] = []
    overall_leakage_passed = True
    min_samples = int(window_config.get("min_samples_per_window") or 1000)

    for window in windows:
        out = _build_window(
            window=window,
            rows=rows,
            dataset_name=dataset_name,
            version=version,
            output_root=output_root,
            storage=storage,
            min_samples=min_samples,
        )
        outputs.append(out["output"])
        diagnostics.append(out["diagnostic"])
        if not out["diagnostic"]["horizon_compliant"] or out["diagnostic"]["future_leakage_violations"] > 0:
            overall_leakage_passed = False

    return DatasetBuildResult(
        status="COMPLETED",
        dataset_name=dataset_name,
        version=version,
        mode=windows[0].mode if windows else str(config.get("mode") or "rolling"),
        windows=len(windows),
        outputs=outputs,
        diagnostics=diagnostics,
        overall_leakage_passed=overall_leakage_passed,
        metadata={
            "input_uri": input_uri,
            "reader": reader,
            "input_rows": len(rows),
            "symbols": list(windows[0].symbols) if windows else [],
        },
    )


def inspect_dataset(
    dataset_name: str,
    output_root: Path,
    window_id: int | None = None,
) -> dict[str, object]:
    """Inspect a built dataset and return aggregated metadata."""
    dataset_dir = output_root / f"dataset={dataset_name}"
    if not dataset_dir.exists():
        return {"status": "NOT_FOUND", "dataset_name": dataset_name, "path": str(dataset_dir)}

    windows: list[dict[str, object]] = []
    for window_dir in sorted(dataset_dir.iterdir()):
        if not window_dir.is_dir() or not window_dir.name.startswith("window_id="):
            continue
        wid = int(window_dir.name.split("=", 1)[1])
        if window_id is not None and wid != window_id:
            continue
        metadata_path = window_dir / "metadata.json"
        meta: dict[str, object] = {}
        if metadata_path.exists():
            meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        windows.append({"window_id": wid, "metadata": meta})

    return {
        "status": "FOUND",
        "dataset_name": dataset_name,
        "path": str(dataset_dir),
        "windows_found": len(windows),
        "windows": windows,
    }


def _build_window(
    window: WindowSpec,
    rows: Sequence[Mapping[str, object]],
    dataset_name: str,
    version: str,
    output_root: Path,
    storage: object,
    min_samples: int,
) -> dict[str, Any]:
    train_rows = _rows_in_range(rows, window.train_start, window.train_end)
    val_rows = _rows_in_range(rows, window.validation_start, window.validation_end)
    test_rows = _rows_in_range(rows, window.test_start, window.test_end)

    base_path = f"datasets/dataset={dataset_name}/version={version}/window_id={window.window_id}"
    train_path = f"{base_path}/train.parquet"
    val_path = f"{base_path}/validation.parquet"
    test_path = f"{base_path}/test.parquet"
    meta_path = f"{base_path}/metadata.json"

    train_bytes = rows_to_parquet_bytes(train_rows)
    val_bytes = rows_to_parquet_bytes(val_rows)
    test_bytes = rows_to_parquet_bytes(test_rows)

    train_uri = storage.put_bytes(train_path, train_bytes, "application/vnd.apache.parquet")
    val_uri = storage.put_bytes(val_path, val_bytes, "application/vnd.apache.parquet")
    test_uri = storage.put_bytes(test_path, test_bytes, "application/vnd.apache.parquet")

    # Build per-window metadata
    diagnostic = diagnose_window(window, rows, min_samples)
    window_meta = {
        "window_id": window.window_id,
        "train_start": window.train_start.isoformat(),
        "train_end": window.train_end.isoformat(),
        "validation_start": window.validation_start.isoformat(),
        "validation_end": window.validation_end.isoformat(),
        "test_start": window.test_start.isoformat(),
        "test_end": window.test_end.isoformat(),
        "horizon_days": window.horizon.days,
        "embargo_days": window.embargo.days,
        "symbols": list(window.symbols),
        "row_counts": {
            "train": len(train_rows),
            "validation": len(val_rows),
            "test": len(test_rows),
        },
        "leakage_checks": {
            "future_leakage_violations": diagnostic.future_leakage_violations,
            "embargo_violations": diagnostic.embargo_violations,
            "horizon_compliant": diagnostic.horizon_compliant,
            "min_samples_met": diagnostic.min_samples_met,
        },
        "paths": {
            "train": train_path,
            "validation": val_path,
            "test": test_path,
        },
        "uris": {
            "train": train_uri,
            "validation": val_uri,
            "test": test_uri,
        },
        "content_hashes": {
            "train": content_hash(train_bytes),
            "validation": content_hash(val_bytes),
            "test": content_hash(test_bytes),
        },
        "version": version,
        "mode": window.mode,
        "created_at": datetime.now(UTC).isoformat(),
    }
    meta_bytes = json.dumps(window_meta, sort_keys=True, indent=2, default=str).encode("utf-8")
    storage.put_bytes(meta_path, meta_bytes, "application/json")

    # Also write metadata.json next to the Parquet files for local inspection
    local_window_dir = output_root / f"dataset={dataset_name}" / f"window_id={window.window_id}"
    local_window_dir.mkdir(parents=True, exist_ok=True)
    (local_window_dir / "metadata.json").write_bytes(meta_bytes)
    (local_window_dir / "train.parquet").write_bytes(train_bytes)
    (local_window_dir / "validation.parquet").write_bytes(val_bytes)
    (local_window_dir / "test.parquet").write_bytes(test_bytes)

    combined_bytes = train_bytes + val_bytes + test_bytes
    output = DatasetWindowOutput(
        window_id=window.window_id,
        train_path=train_path,
        validation_path=val_path,
        test_path=test_path,
        metadata_path=meta_path,
        train_rows=len(train_rows),
        validation_rows=len(val_rows),
        test_rows=len(test_rows),
        content_hash=content_hash(combined_bytes),
    )

    return {"output": output, "diagnostic": diagnostic.to_dict()}


def _rows_in_range(
    rows: Sequence[Mapping[str, object]],
    start: datetime,
    end: datetime,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in rows:
        ts = _parse_ts(row.get("ts"))
        if ts is not None and start <= ts <= end:
            result.append(dict(row))
    return result


def _parse_ts(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _normalize_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Normalize rows with deterministic sort."""
    normalized: list[dict[str, object]] = []
    for row in rows:
        item = {str(key): value for key, value in dict(row).items()}
        item["symbol"] = str(item.get("symbol") or "UNKNOWN").upper()
        item["ts"] = str(item.get("ts") or "")
        normalized.append(item)
    return sorted(normalized, key=lambda r: (str(r.get("symbol") or ""), str(r.get("ts") or "")))


def _config_path(config: Mapping[str, object], key: str, default: Path) -> Path:
    value = config.get(key)
    if value in (None, ""):
        return default
    return Path(str(value))


def _window_config(config: Mapping[str, object]) -> dict[str, object]:
    nested = config.get("sliding_window")
    if isinstance(nested, Mapping):
        return {**dict(config), **dict(nested)}
    return dict(config)


def _input_path(config: Mapping[str, object], lake_root: Path) -> Path:
    configured = config.get("input_path") or config.get("source_path")
    if configured:
        return Path(str(configured))
    # Default: try features output, then silver, then bronze
    features = lake_root / "features"
    if features.exists():
        return features
    silver = lake_root / "silver" / "market_bars"
    if silver.exists():
        return silver
    bronze = lake_root / "bronze" / "market_bars"
    if bronze.exists():
        return bronze
    return lake_root / "raw"


def _bool(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
