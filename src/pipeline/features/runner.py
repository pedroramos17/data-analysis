"""Phase 5 feature extraction runner."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.pipeline.features.base import (
    FeatureRunRecord,
    RuntimeTimer,
    normalize_input_rows,
    read_feature_input_rows,
    register_feature_run,
    write_feature_rows,
)
from src.pipeline.features.graph import compute_graph_features
from src.pipeline.features.lob import compute_lob_features
from src.pipeline.features.multifractal import compute_multifractal_features
from src.pipeline.features.price_volume import compute_price_volume_features
from src.pipeline.features.regime import compute_regime_features
from src.pipeline.features.risk import compute_risk_features
from src.providers.registry import ProviderRegistry, build_provider_registry

FeatureComputer = Callable[..., list[dict[str, object]]]
DEFAULT_FEATURE_GROUPS = ("price_volume", "lob", "multifractal", "regime", "risk", "graph")
FEATURE_GROUPS: dict[str, FeatureComputer] = {
    "price_volume": compute_price_volume_features,
    "lob": compute_lob_features,
    "multifractal": compute_multifractal_features,
    "regime": compute_regime_features,
    "risk": compute_risk_features,
    "graph": compute_graph_features,
}
GROUP_ALIASES = {"knowledge_graph": "graph", "graphs": "graph"}


@dataclass(frozen=True, slots=True)
class FeaturePipelineResult:
    """Feature extraction result payload."""

    status: str
    version: str
    feature_sets: tuple[str, ...]
    input_uri: str
    input_rows: int
    rows: int
    columns: int
    outputs: list[dict[str, object]]
    feature_runs: list[FeatureRunRecord]
    runtime: dict[str, object]
    metadata_rows: int
    no_future_leakage: bool = True
    rolling_window_policy: str = "past_and_current_rows_only_ordered_by_symbol_time"
    reader: str = ""
    errors: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable result."""
        return {
            "status": self.status,
            "version": self.version,
            "groups": list(self.feature_sets),
            "feature_sets": list(self.feature_sets),
            "input_uri": self.input_uri,
            "input_rows": self.input_rows,
            "rows": self.rows,
            "columns": self.columns,
            "outputs": [dict(output) for output in self.outputs],
            "feature_runs": [record.to_dict() for record in self.feature_runs],
            "metadata_rows": self.metadata_rows,
            "runtime": dict(self.runtime),
            "reader": self.reader,
            "no_future_leakage": self.no_future_leakage,
            "rolling_window_policy": self.rolling_window_policy,
            "errors": [dict(error) for error in self.errors],
        }


def run_feature_pipeline(
    config: Mapping[str, object],
    registry: ProviderRegistry | None = None,
) -> FeaturePipelineResult:
    """Build versioned feature outputs from bronze/silver Parquet inputs."""
    active_registry = registry or build_provider_registry(load_runtime_settings())
    lake_root = _config_path(config, "lake_root", active_registry.settings.storage.local_root)
    input_path = _input_path(config, lake_root)
    version = str(config.get("version") or "phase5_v1")
    feature_sets = _feature_sets(config)
    window = int(config.get("rolling_window") or config.get("window") or 20)
    long_window = int(config.get("long_window") or max(window * 3, 60))
    timer = RuntimeTimer()
    raw_rows, reader, input_uri = read_feature_input_rows(
        input_path,
        require_duckdb=_bool(config.get("require_duckdb"), False),
    )
    rows = _filter_rows(normalize_input_rows(raw_rows), config)
    outputs: list[dict[str, object]] = []
    feature_runs: list[FeatureRunRecord] = []
    total_rows = 0
    max_columns = 0
    started_at = datetime.now(UTC)
    storage = active_registry.get_storage()
    for feature_set in feature_sets:
        computed = _compute_feature_set(feature_set, rows, version, window, long_window)
        total_rows += len(computed)
        max_columns = max(max_columns, max((len(row) for row in computed), default=0))
        feature_outputs = write_feature_rows(storage, feature_set, version, computed)
        outputs.extend(feature_outputs)
        for output in feature_outputs:
            record = FeatureRunRecord(
                feature_set=feature_set,
                version=version,
                input_uri=input_uri,
                output_uri=str(output["uri"]),
                config_json=_config_metadata(config, feature_sets),
                rows=int(output["rows"]),
                columns=int(output["columns"]),
                started_at=started_at,
                finished_at=datetime.now(UTC),
                status="COMPLETED",
            )
            feature_runs.append(_register(active_registry, record))
    runtime = timer.finish(total_rows).to_dict()
    return FeaturePipelineResult(
        status="COMPLETED",
        version=version,
        feature_sets=feature_sets,
        input_uri=input_uri,
        input_rows=len(rows),
        rows=total_rows,
        columns=max_columns,
        outputs=outputs,
        feature_runs=feature_runs,
        metadata_rows=len(feature_runs),
        runtime=runtime,
        reader=reader,
    )


def _compute_feature_set(
    feature_set: str,
    rows: Sequence[Mapping[str, object]],
    version: str,
    window: int,
    long_window: int,
) -> list[dict[str, object]]:
    if feature_set == "multifractal":
        return compute_multifractal_features(
            rows,
            version=version,
            short_window=window,
            long_window=long_window,
        )
    return FEATURE_GROUPS[feature_set](rows, version=version, window=window)


def _register(registry: ProviderRegistry, record: FeatureRunRecord) -> FeatureRunRecord:
    record_id = register_feature_run(registry.settings.database, record)
    return FeatureRunRecord(
        feature_set=record.feature_set,
        version=record.version,
        input_uri=record.input_uri,
        output_uri=record.output_uri,
        config_json=record.config_json,
        rows=record.rows,
        columns=record.columns,
        started_at=record.started_at,
        finished_at=record.finished_at,
        status=record.status,
        error_json=record.error_json,
        id=record_id,
    )


def _filter_rows(rows: Sequence[Mapping[str, object]], config: Mapping[str, object]) -> list[dict[str, object]]:
    universe = {symbol.upper() for symbol in _string_list(config.get("universe", []))}
    start = str(config.get("start") or "1900-01-01")
    end = str(config.get("end") or "2999-12-31")
    timeframe = str(config.get("timeframe") or "")
    filtered: list[dict[str, object]] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        ts = str(row.get("ts") or "")
        if universe and symbol not in universe:
            continue
        if timeframe and str(row.get("timeframe") or "") != timeframe:
            continue
        if ts[:10] < start[:10] or ts[:10] > end[:10]:
            continue
        filtered.append(dict(row))
    return filtered


def _feature_sets(config: Mapping[str, object]) -> tuple[str, ...]:
    raw = config.get("feature_sets", config.get("groups", DEFAULT_FEATURE_GROUPS))
    values = _string_list(raw)
    selected = tuple(GROUP_ALIASES.get(value, value) for value in values) or DEFAULT_FEATURE_GROUPS
    invalid = sorted(set(selected) - set(FEATURE_GROUPS))
    if invalid:
        raise ValueError(
            f"Invalid feature groups {invalid!r}; expected one of {sorted(FEATURE_GROUPS)!r}"
        )
    return selected


def _input_path(config: Mapping[str, object], lake_root: Path) -> Path:
    configured = config.get("input_path") or config.get("source_path")
    if configured:
        return Path(str(configured))
    silver = lake_root / "silver" / "market_bars"
    if silver.exists():
        return silver
    bronze = lake_root / "bronze" / "market_bars"
    if bronze.exists():
        return bronze
    return lake_root / "raw"


def _config_metadata(config: Mapping[str, object], feature_sets: Sequence[str]) -> dict[str, object]:
    return {
        "version": str(config.get("version") or "phase5_v1"),
        "feature_sets": list(feature_sets),
        "rolling_window": int(config.get("rolling_window") or config.get("window") or 20),
        "long_window": int(config.get("long_window") or max(int(config.get("rolling_window") or config.get("window") or 20) * 3, 60)),
        "no_future_leakage": True,
    }


def _config_path(config: Mapping[str, object], key: str, default: Path) -> Path:
    value = config.get(key)
    if value in (None, ""):
        return default
    return Path(str(value))


def _string_list(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            text = text.strip("[]")
        return [item.strip().strip("'\"") for item in text.split(",") if item.strip()]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise ValueError(f"Invalid list value {value!r}; expected list or comma string")


def _bool(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
