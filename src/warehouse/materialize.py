"""Materialization functions for DuckDB warehouse datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.providers.registry import build_provider_registry
from src.warehouse.duckdb_context import (
    DuckDBWarehouseContext,
    default_dataset_globs,
    sql_literal,
)
from src.warehouse.views import register_warehouse_views


@dataclass(frozen=True, slots=True)
class MaterializationResult:
    """Result metadata for a DuckDB materialized dataset."""

    output_path: Path
    row_count: int
    source_view: str


def build_research_panel(
    universe: Sequence[str],
    start: str,
    end: str,
    timeframe: str,
    *,
    context: DuckDBWarehouseContext | None = None,
    output_path: str | Path | None = None,
) -> MaterializationResult:
    """Build and materialize the joined research panel."""
    active_context = context or context_from_config({})
    register_warehouse_views(
        active_context,
        default_dataset_globs(active_context.lake_root),
    )
    sql = research_panel_sql(universe, start, end, timeframe)
    target = Path(
        output_path or active_context.lake_root / "gold" / "research_panel.parquet"
    )
    return _materialize(active_context, sql, target, "v_signal_panel")


def build_training_dataset(config: Mapping[str, object]) -> MaterializationResult:
    """Build a model-training dataset without materializing through pandas."""
    context = context_from_config(config)
    register_warehouse_views(context, default_dataset_globs(context.lake_root))
    sql = training_dataset_sql(config)
    output_path = _config_path(
        config,
        "output_path",
        context.lake_root / "gold" / "training_dataset.parquet",
    )
    return _materialize(context, sql, output_path, "v_signal_panel")


def build_backtest_dataset(config: Mapping[str, object]) -> MaterializationResult:
    """Build a backtest panel from signals, bars, returns, and weights."""
    context = context_from_config(config)
    register_warehouse_views(context, default_dataset_globs(context.lake_root))
    sql = filtered_view_sql("v_backtest_panel", config)
    output_path = _config_path(
        config,
        "output_path",
        context.lake_root / "gold" / "backtest_dataset.parquet",
    )
    return _materialize(context, sql, output_path, "v_backtest_panel")


def materialize_feature_store(config: Mapping[str, object]) -> MaterializationResult:
    """Materialize feature-store rows from multifractal and LOB feature views."""
    context = context_from_config(config)
    register_warehouse_views(context, default_dataset_globs(context.lake_root))
    sql = filtered_feature_store_sql(config)
    output_path = _config_path(
        config,
        "output_path",
        context.lake_root / "features" / "feature_store.parquet",
    )
    return _materialize(context, sql, output_path, "feature_store")


def build_panel_from_config(config: Mapping[str, object]) -> MaterializationResult:
    """Build the research panel from a CLI config mapping."""
    context = context_from_config(config)
    return build_research_panel(
        _string_list(config.get("universe", [])),
        str(config.get("start", "1900-01-01")),
        str(config.get("end", "2999-12-31")),
        str(config.get("timeframe", "1d")),
        context=context,
        output_path=_config_path(
            config,
            "output_path",
            context.lake_root / "gold" / "research_panel.parquet",
        ),
    )


def context_from_config(config: Mapping[str, object]) -> DuckDBWarehouseContext:
    """Create a DuckDB context from runtime settings plus materialization config."""
    settings = load_runtime_settings()
    lake_root = _config_path(config, "lake_root", settings.duckdb.data_lake_root)
    database_path = _config_path(config, "duckdb_path", settings.duckdb.database_path)
    cache_root = _optional_config_path(config, "cache_root")
    context = DuckDBWarehouseContext(database_path, lake_root, cache_root)
    prefixes = _string_list(config.get("object_store_prefixes", []))
    if prefixes and settings.storage.uses_remote_object_storage():
        registry = build_provider_registry(settings)
        mirror = context.mirror_storage_prefixes(registry.get_storage(), prefixes)
        return DuckDBWarehouseContext(database_path, mirror.local_root, cache_root)
    return context


def research_panel_sql(
    universe: Sequence[str],
    start: str,
    end: str,
    timeframe: str,
) -> str:
    """Return SQL for the research panel filters."""
    filters = [
        f"ts >= cast({sql_literal(start)} as timestamp)",
        f"ts <= cast({sql_literal(end)} as timestamp)",
        f"timeframe = {sql_literal(timeframe)}",
    ]
    if universe:
        filters.append(_universe_filter(universe))
    return (
        "select * from v_signal_panel where "
        + " and ".join(filters)
        + " order by symbol, ts"
    )


def training_dataset_sql(config: Mapping[str, object]) -> str:
    """Return SQL for a supervised training dataset."""
    base_sql = filtered_view_sql("v_signal_panel", config)
    target_column = str(config.get("target_column", "log_return"))
    _validate_identifier(target_column)
    return (
        "select * from ("
        + base_sql
        + f") where {target_column} is not null order by symbol, ts"
    )


def filtered_view_sql(view_name: str, config: Mapping[str, object]) -> str:
    """Return SQL selecting a filtered warehouse view."""
    _validate_identifier(view_name)
    universe = _string_list(config.get("universe", []))
    start = str(config.get("start", "1900-01-01"))
    end = str(config.get("end", "2999-12-31"))
    timeframe = str(config.get("timeframe", "1d"))
    filters = [
        f"ts >= cast({sql_literal(start)} as timestamp)",
        f"ts <= cast({sql_literal(end)} as timestamp)",
        f"timeframe = {sql_literal(timeframe)}",
    ]
    if universe:
        filters.append(_universe_filter(universe))
    return f"select * from {view_name} where " + " and ".join(filters)


def filtered_feature_store_sql(config: Mapping[str, object]) -> str:
    """Return SQL for the materialized feature store."""
    base = """
    select
        symbol,
        asset_type,
        ts,
        timeframe,
        feature_set,
        version,
        feature_name,
        feature_value,
        values_json,
        cast(NULL as VARCHAR) as bid_levels_json,
        cast(NULL as VARCHAR) as ask_levels_json,
        cast(NULL as DOUBLE) as spread,
        cast(NULL as DOUBLE) as imbalance,
        cast(NULL as DOUBLE) as bid_depth,
        cast(NULL as DOUBLE) as ask_depth,
        source
    from v_multifractal_features
    union all
    select
        symbol,
        asset_type,
        ts,
        timeframe,
        feature_set,
        version,
        feature_name,
        feature_value,
        cast(NULL as VARCHAR) as values_json,
        bid_levels_json,
        ask_levels_json,
        spread,
        imbalance,
        bid_depth,
        ask_depth,
        source
    from v_lob_features
    """
    filtered = filtered_view_sql("feature_store_source", config).replace(
        "from feature_store_source",
        "from (" + base + ") feature_store_source",
    )
    return filtered + " order by symbol, ts, feature_set"


def _materialize(
    context: DuckDBWarehouseContext,
    sql: str,
    output_path: Path,
    source_view: str,
) -> MaterializationResult:
    row_count = int(context.scalar("select count(*) from (" + sql + ")"))
    context.materialize(sql, output_path)
    return MaterializationResult(output_path, row_count, source_view)


def _universe_filter(universe: Sequence[str]) -> str:
    values = ", ".join(sql_literal(symbol.upper()) for symbol in universe)
    return f"upper(symbol) in ({values})"


def _string_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise ValueError(f"Invalid list value {value!r}; expected list or comma string")


def _config_path(config: Mapping[str, object], key: str, default: Path) -> Path:
    value = config.get(key)
    if value in (None, ""):
        return default
    return Path(str(value))


def _optional_config_path(config: Mapping[str, object], key: str) -> Path | None:
    value = config.get(key)
    if value in (None, ""):
        return None
    return Path(str(value))


def _validate_identifier(value: str) -> None:
    if value and value.replace("_", "").isalnum() and value[0].isalpha():
        return
    raise ValueError(f"Invalid identifier {value!r}")
