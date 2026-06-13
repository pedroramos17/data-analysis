"""Portable SQLAlchemy schema for the Quant MVP database contract.

The existing Django models and migrations remain authoritative for the web app.
This module defines the provider-neutral MVP tables used by the SQLite/Postgres
compatibility layer and by Alembic migrations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.types import TypeDecorator

from src.config.settings import DatabaseSettings

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CompatibleJSON(TypeDecorator):
    """Store JSON as JSONB on Postgres and text JSON on SQLite.

    Example:
        `Column("metadata_json", CompatibleJSON(), nullable=False)`
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        """Return the best JSON storage type for the active dialect."""
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        """Serialize JSON values for text-only dialects."""
        if value is None or dialect.name == "postgresql":
            return value
        return json.dumps(value, sort_keys=True)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Deserialize text JSON values returned by SQLite."""
        if value is None or dialect.name == "postgresql":
            return value
        if isinstance(value, dict | list):
            return value
        return json.loads(value)


def _id_column() -> Column[int]:
    return Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )


def _created_at_column() -> Column[Any]:
    return Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


def _updated_at_column() -> Column[Any]:
    return Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


assets = Table(
    "assets",
    metadata,
    _id_column(),
    Column("symbol", String(64), nullable=False),
    Column("exchange", String(80), nullable=False, default=""),
    Column("asset_type", String(40), nullable=False, default="equity"),
    Column("currency", String(12), nullable=False, default="USD"),
    Column("sector", String(128), nullable=False, default=""),
    Column("metadata_json", CompatibleJSON(), nullable=False, default=dict),
    _created_at_column(),
    _updated_at_column(),
    UniqueConstraint("symbol", "exchange", "asset_type", name="uq_assets_identity"),
    Index("ix_assets_symbol_exchange", "symbol", "exchange"),
)

ingestion_runs = Table(
    "ingestion_runs",
    metadata,
    _id_column(),
    Column("source", String(120), nullable=False),
    Column("asset_type", String(40), nullable=False, default=""),
    Column("symbol", String(64), nullable=False, default=""),
    Column("timeframe", String(32), nullable=False, default=""),
    Column("start_ts", DateTime(timezone=True), nullable=True),
    Column("end_ts", DateTime(timezone=True), nullable=True),
    Column("status", String(32), nullable=False),
    Column("rows_written", Integer, nullable=False, default=0),
    Column("rows_deduplicated", Integer, nullable=False, default=0),
    Column("missing_ratio", Float, nullable=False, default=0.0),
    Column("output_uri", String(1200), nullable=False, default=""),
    Column("content_hash", String(128), nullable=False, default=""),
    Column(
        "started_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("error_json", CompatibleJSON(), nullable=False, default=dict),
    Column("stats_json", CompatibleJSON(), nullable=False, default=dict),
    Column("error", Text, nullable=False, default=""),
    Index("ix_ingestion_runs_source_started_at", "source", "started_at"),
    Index("ix_ingestion_runs_identity", "source", "asset_type", "symbol", "timeframe"),
    Index("ix_ingestion_runs_output_hash", "output_uri", "content_hash"),
)

market_bars = Table(
    "market_bars",
    metadata,
    _id_column(),
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("timeframe", String(16), nullable=False),
    Column("open", Float, nullable=True),
    Column("high", Float, nullable=True),
    Column("low", Float, nullable=True),
    Column("close", Float, nullable=True),
    Column("volume", Float, nullable=True),
    Column("source", String(120), nullable=False),
    Column(
        "ingestion_run_id",
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
        nullable=True,
    ),
    UniqueConstraint(
        "asset_id",
        "ts",
        "timeframe",
        "source",
        name="uq_market_bars_asset_ts_timeframe_source",
    ),
    Index("ix_market_bars_asset_ts", "asset_id", "ts"),
    Index("ix_market_bars_source_ts", "source", "ts"),
)

lob_snapshots = Table(
    "lob_snapshots",
    metadata,
    _id_column(),
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("bid_levels_json", CompatibleJSON(), nullable=False, default=list),
    Column("ask_levels_json", CompatibleJSON(), nullable=False, default=list),
    Column("spread", Float, nullable=True),
    Column("imbalance", Float, nullable=True),
    Column("source", String(120), nullable=False),
    UniqueConstraint(
        "asset_id",
        "ts",
        "source",
        name="uq_lob_snapshots_asset_ts_source",
    ),
    Index("ix_lob_snapshots_asset_ts", "asset_id", "ts"),
)

features = Table(
    "features",
    metadata,
    _id_column(),
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("feature_set", String(180), nullable=False),
    Column("values_json", CompatibleJSON(), nullable=False, default=dict),
    Column("version", String(64), nullable=False),
    UniqueConstraint(
        "asset_id",
        "ts",
        "feature_set",
        "version",
        name="uq_features_asset_ts_set_version",
    ),
    Index("ix_features_asset_ts", "asset_id", "ts"),
    Index("ix_features_feature_set_version", "feature_set", "version"),
)

feature_runs = Table(
    "feature_runs",
    metadata,
    _id_column(),
    Column("feature_set", String(180), nullable=False),
    Column("version", String(64), nullable=False),
    Column("input_uri", String(1200), nullable=False, default=""),
    Column("output_uri", String(1200), nullable=False, default=""),
    Column("config_json", CompatibleJSON(), nullable=False, default=dict),
    Column("rows", Integer, nullable=False, default=0),
    Column("columns", Integer, nullable=False, default=0),
    Column(
        "started_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("status", String(32), nullable=False),
    Column("error_json", CompatibleJSON(), nullable=False, default=dict),
    Index("ix_feature_runs_set_version", "feature_set", "version"),
    Index("ix_feature_runs_output_uri", "output_uri"),
)

signals = Table(
    "signals",
    metadata,
    _id_column(),
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("model_name", String(180), nullable=False),
    Column("model_version", String(64), nullable=False),
    Column("horizon", String(32), nullable=False),
    Column("signal", Float, nullable=False),
    Column("confidence", Float, nullable=True),
    Column("explanation_json", CompatibleJSON(), nullable=False, default=dict),
    UniqueConstraint(
        "asset_id",
        "ts",
        "model_name",
        "model_version",
        "horizon",
        name="uq_signals_asset_ts_model_horizon",
    ),
    Index("ix_signals_asset_ts", "asset_id", "ts"),
    Index("ix_signals_model_version", "model_name", "model_version"),
)

backtest_runs = Table(
    "backtest_runs",
    metadata,
    _id_column(),
    Column("name", String(180), nullable=False),
    Column("config_json", CompatibleJSON(), nullable=False, default=dict),
    Column("metrics_json", CompatibleJSON(), nullable=False, default=dict),
    _created_at_column(),
    Index("ix_backtest_runs_created_at", "created_at"),
)

risk_runs = Table(
    "risk_runs",
    metadata,
    _id_column(),
    Column("universe", String(500), nullable=False),
    Column("config_json", CompatibleJSON(), nullable=False, default=dict),
    Column("metrics_json", CompatibleJSON(), nullable=False, default=dict),
    _created_at_column(),
    Index("ix_risk_runs_created_at", "created_at"),
)

model_artifacts = Table(
    "model_artifacts",
    metadata,
    _id_column(),
    Column("model_name", String(180), nullable=False),
    Column("model_version", String(64), nullable=False),
    Column("artifact_uri", String(1200), nullable=False),
    Column("metadata_json", CompatibleJSON(), nullable=False, default=dict),
    _created_at_column(),
    UniqueConstraint(
        "model_name",
        "model_version",
        name="uq_model_artifacts_name_version",
    ),
    Index("ix_model_artifacts_model_version", "model_name", "model_version"),
)

pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    _id_column(),
    Column("name", String(180), nullable=False),
    Column("config_json", CompatibleJSON(), nullable=False, default=dict),
    Column("status", String(32), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("cost_estimate_json", CompatibleJSON(), nullable=False, default=dict),
    Column("efficiency_json", CompatibleJSON(), nullable=False, default=dict),
    Column("error_json", CompatibleJSON(), nullable=False, default=dict),
    _created_at_column(),
    _updated_at_column(),
    Index("ix_pipeline_runs_name_created_at", "name", "created_at"),
    Index("ix_pipeline_runs_status", "status"),
)

pipeline_tasks = Table(
    "pipeline_tasks",
    metadata,
    _id_column(),
    Column("pipeline_run_id", ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
    Column("task_name", String(180), nullable=False),
    Column("status", String(32), nullable=False),
    Column("input_hash", String(128), nullable=False, default=""),
    Column("output_uri", String(1200), nullable=False, default=""),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("duration_seconds", Float, nullable=False, default=0.0),
    Column("retry_count", Integer, nullable=False, default=0),
    Column("error_json", CompatibleJSON(), nullable=False, default=dict),
    Column("metadata_json", CompatibleJSON(), nullable=False, default=dict),
    UniqueConstraint("pipeline_run_id", "task_name", name="uq_pipeline_tasks_run_task"),
    Index("ix_pipeline_tasks_run_status", "pipeline_run_id", "status"),
    Index("ix_pipeline_tasks_hash", "task_name", "input_hash"),
)

CORE_TABLES = (
    assets,
    market_bars,
    lob_snapshots,
    features,
    feature_runs,
    signals,
    backtest_runs,
    risk_runs,
    model_artifacts,
    pipeline_runs,
    pipeline_tasks,
    ingestion_runs,
)
CORE_TABLE_NAMES = tuple(table.name for table in CORE_TABLES)


def create_core_tables(engine: Engine) -> None:
    """Create missing MVP tables without mutating existing tables."""
    metadata.create_all(engine, tables=list(CORE_TABLES), checkfirst=True)


def drop_core_tables(engine: Engine) -> None:
    """Drop MVP tables for isolated integration-test databases only."""
    metadata.drop_all(engine, tables=list(CORE_TABLES), checkfirst=True)


def build_core_engine(database_settings: DatabaseSettings, **kwargs: Any) -> Engine:
    """Build a SQLAlchemy engine from project runtime database settings."""
    return create_engine(sqlalchemy_url_from_database_settings(database_settings), **kwargs)


def sqlalchemy_url_from_database_settings(settings: DatabaseSettings) -> str:
    """Return a SQLAlchemy URL for SQLite or Postgres runtime settings."""
    if settings.db_mode == "sqlite":
        return _sqlite_url(settings.sqlite_path)
    return _postgres_sqlalchemy_url(settings.postgres_url)


def _sqlite_url(sqlite_path: Path) -> str:
    return f"sqlite:///{sqlite_path.as_posix()}"


def _postgres_sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    return database_url
