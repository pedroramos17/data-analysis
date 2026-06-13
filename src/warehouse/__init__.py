"""DuckDB analytical warehouse over local or mirrored Parquet datasets."""

from __future__ import annotations

from src.warehouse.duckdb_context import DuckDBWarehouseContext
from src.warehouse.materialize import (
    MaterializationResult,
    build_backtest_dataset,
    build_research_panel,
    build_training_dataset,
    materialize_feature_store,
)

__all__ = [
    "DuckDBWarehouseContext",
    "MaterializationResult",
    "build_backtest_dataset",
    "build_research_panel",
    "build_training_dataset",
    "materialize_feature_store",
]
