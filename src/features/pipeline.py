"""Feature-store materialization pipeline over DuckDB/Parquet."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.features.definitions import DEFAULT_FEATURE_GROUPS, DEFAULT_FEATURE_VERSION
from src.features.metadata import persist_feature_metadata
from src.features.sql import feature_store_sql
from src.warehouse.duckdb_context import DuckDBWarehouseContext, default_dataset_globs
from src.warehouse.materialize import context_from_config
from src.warehouse.views import register_warehouse_views


@dataclass(frozen=True, slots=True)
class FeaturePipelineConfig:
    """Config for materializing versioned feature-store outputs."""

    version: str = DEFAULT_FEATURE_VERSION
    groups: tuple[str, ...] = DEFAULT_FEATURE_GROUPS
    universe: tuple[str, ...] = ()
    start: str = "1900-01-01"
    end: str = "2999-12-31"
    timeframe: str = "1d"
    lake_root: Path | None = None
    duckdb_path: Path | None = None
    output_path: Path | None = None
    cache_root: Path | None = None
    object_store_prefixes: tuple[str, ...] = ()
    database_url: str = ""
    persist_metadata: bool = False
    metadata_row_limit: int = 100_000

    @classmethod
    def from_mapping(cls, config: Mapping[str, object]) -> "FeaturePipelineConfig":
        """Build config from a JSON/YAML mapping."""
        version = str(config.get("version") or DEFAULT_FEATURE_VERSION)
        return cls(
            version=version,
            groups=tuple(_string_list(config.get("groups", DEFAULT_FEATURE_GROUPS))),
            universe=tuple(_string_list(config.get("universe", ()))),
            start=str(config.get("start", "1900-01-01")),
            end=str(config.get("end", "2999-12-31")),
            timeframe=str(config.get("timeframe", "1d")),
            lake_root=_optional_path(config.get("lake_root")),
            duckdb_path=_optional_path(config.get("duckdb_path")),
            output_path=_optional_path(config.get("output_path")),
            cache_root=_optional_path(config.get("cache_root")),
            object_store_prefixes=tuple(_string_list(config.get("object_store_prefixes", ()))),
            database_url=str(config.get("database_url") or ""),
            persist_metadata=_bool_value(config.get("persist_metadata", False)),
            metadata_row_limit=int(config.get("metadata_row_limit", 100_000)),
        )

    def materialization_mapping(self) -> dict[str, object]:
        """Return the subset consumed by the existing warehouse context builder."""
        payload: dict[str, object] = {
            "object_store_prefixes": list(self.object_store_prefixes),
        }
        if self.lake_root is not None:
            payload["lake_root"] = self.lake_root
        if self.duckdb_path is not None:
            payload["duckdb_path"] = self.duckdb_path
        if self.cache_root is not None:
            payload["cache_root"] = self.cache_root
        return payload


@dataclass(frozen=True, slots=True)
class FeatureStoreBuildResult:
    """Result metadata for one feature-store materialization."""

    output_path: Path
    row_count: int
    version: str
    groups: tuple[str, ...]
    metadata_rows: int = 0


def build_feature_store(
    config: FeaturePipelineConfig | Mapping[str, object],
    *,
    context: DuckDBWarehouseContext | None = None,
) -> FeatureStoreBuildResult:
    """Materialize versioned feature rows from DuckDB warehouse views."""
    active_config = (
        config if isinstance(config, FeaturePipelineConfig) else FeaturePipelineConfig.from_mapping(config)
    )
    active_context = context or context_from_config(active_config.materialization_mapping())
    register_warehouse_views(active_context, default_dataset_globs(active_context.lake_root))
    sql = feature_store_sql(
        version=active_config.version,
        groups=active_config.groups,
        universe=active_config.universe,
        start=active_config.start,
        end=active_config.end,
        timeframe=active_config.timeframe,
    )
    output_path = active_config.output_path or versioned_feature_output_path(
        active_context.lake_root,
        active_config.version,
    )
    row_count = int(active_context.scalar("select count(*) from (" + sql + ")"))
    active_context.materialize(sql, output_path)
    metadata_rows = _persist_metadata_if_requested(active_config, active_context, sql, row_count)
    return FeatureStoreBuildResult(
        output_path=output_path,
        row_count=row_count,
        version=active_config.version,
        groups=active_config.groups,
        metadata_rows=metadata_rows,
    )


def versioned_feature_output_path(lake_root: str | Path, version: str) -> Path:
    """Return the default versioned feature-store output path."""
    return Path(lake_root) / "gold" / "features" / f"version={version}" / "feature_store.parquet"


def _persist_metadata_if_requested(
    config: FeaturePipelineConfig,
    context: DuckDBWarehouseContext,
    sql: str,
    row_count: int,
) -> int:
    if not config.persist_metadata or not config.database_url:
        return 0
    if row_count > config.metadata_row_limit:
        raise ValueError(
            f"Invalid feature metadata row_count={row_count}; expected <= "
            f"metadata_row_limit={config.metadata_row_limit}"
        )
    return persist_feature_metadata(config.database_url, context.query(sql))


def _string_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise ValueError(f"Invalid list value {value!r}; expected list or comma string")


def _optional_path(value: object) -> Path | None:
    if value in (None, ""):
        return None
    return Path(str(value))


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
