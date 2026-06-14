"""Tests for the SQLite/Postgres database compatibility schema."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from uuid import uuid4

try:
    from sqlalchemy import MetaData, create_engine, inspect, select, text
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    from src.config.settings import load_runtime_settings
    from src.database.core_schema import (
        CORE_TABLE_NAMES,
        assets,
        build_core_engine,
        create_core_tables,
        metadata,
        sqlalchemy_url_from_database_settings,
    )
except ImportError:
    SQLALCHEMY_AVAILABLE = False
else:
    SQLALCHEMY_AVAILABLE = True


@unittest.skipUnless(SQLALCHEMY_AVAILABLE, "SQLAlchemy is required for schema tests")
class DatabaseCompatibilitySchemaTests(unittest.TestCase):
    """The MVP database contract must stay portable across SQLite/Postgres."""

    def test_sqlite_schema_creation_is_idempotent(self) -> None:
        """SQLite local mode can create the core tables repeatedly."""
        engine = create_engine("sqlite:///:memory:")

        create_core_tables(engine)
        create_core_tables(engine)

        inspector = inspect(engine)
        self.assertEqual(set(CORE_TABLE_NAMES), set(inspector.get_table_names()))
        for table_name, expected_columns in EXPECTED_COLUMNS.items():
            with self.subTest(table_name=table_name):
                self.assertEqual(_column_names(inspector, table_name), expected_columns)

    def test_sqlite_json_columns_round_trip_as_text_json(self) -> None:
        """SQLite stores JSON compatibility columns as text and round-trips them."""
        engine = create_engine("sqlite:///:memory:")
        create_core_tables(engine)

        metadata_column = _column_types(inspect(engine), "assets")["metadata_json"]
        self.assertIn("TEXT", metadata_column.upper())

        with engine.begin() as connection:
            connection.execute(
                assets.insert().values(
                    symbol="AAPL",
                    exchange="NASDAQ",
                    asset_type="equity",
                    currency="USD",
                    sector="technology",
                    metadata_json={"figi": "BBG000B9XRY4"},
                )
            )
            value = connection.execute(select(assets.c.metadata_json)).scalar_one()

        self.assertEqual(value, {"figi": "BBG000B9XRY4"})

    def test_postgres_ddl_uses_jsonb_for_json_columns(self) -> None:
        """Postgres uses JSONB while SQLite keeps text JSON fallback."""
        postgres_ddl = str(CreateTable(assets).compile(dialect=postgresql.dialect()))
        sqlite_ddl = str(CreateTable(assets).compile(dialect=sqlite.dialect()))

        self.assertIn("metadata_json JSONB", postgres_ddl)
        self.assertIn("metadata_json TEXT", sqlite_ddl)

    def test_runtime_database_settings_build_sqlalchemy_urls(self) -> None:
        """Runtime DB mode maps to SQLAlchemy URLs without changing defaults."""
        local = load_runtime_settings(env={}, base_dir=Path("/tmp/quant-mvp"))
        cloud = load_runtime_settings(
            env={
                "DB_MODE": "postgres",
                "DATABASE_URL": "postgresql://quant:secret@db.example:5432/quant",
            },
            base_dir=Path("/tmp/quant-mvp"),
        )

        self.assertEqual(
            sqlalchemy_url_from_database_settings(local.database),
            "sqlite:////tmp/quant-mvp/db.sqlite3",
        )
        self.assertEqual(
            sqlalchemy_url_from_database_settings(cloud.database),
            "postgresql+psycopg://quant:secret@db.example:5432/quant",
        )
        engine = build_core_engine(local.database)
        self.assertEqual(engine.url.drivername, "sqlite")
        engine.dispose()

    @unittest.skipUnless(
        os.environ.get("POSTGRES_TEST_DATABASE_URL"),
        "set POSTGRES_TEST_DATABASE_URL to run Postgres schema integration test",
    )
    def test_optional_postgres_schema_integration(self) -> None:
        """Optional Docker-backed Postgres test creates the schema in isolation."""
        engine = create_engine(os.environ["POSTGRES_TEST_DATABASE_URL"])
        schema_name = f"compat_{uuid4().hex}"

        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            schema_metadata = MetaData(schema=schema_name)
            for table in metadata.sorted_tables:
                table.to_metadata(schema_metadata)
            try:
                schema_metadata.create_all(connection, checkfirst=True)
                inspector = inspect(connection)
                self.assertEqual(
                    set(CORE_TABLE_NAMES),
                    set(inspector.get_table_names(schema=schema_name)),
                )
                column_types = {
                    column["name"]: str(column["type"])
                    for column in inspector.get_columns("assets", schema=schema_name)
                }
                self.assertIn("JSONB", column_types["metadata_json"].upper())
            finally:
                connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))


def _column_names(inspector: object, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _column_types(inspector: object, table_name: str) -> dict[str, str]:
    return {
        column["name"]: str(column["type"])
        for column in inspector.get_columns(table_name)
    }


EXPECTED_COLUMNS = {
    "assets": {
        "id",
        "symbol",
        "exchange",
        "asset_type",
        "currency",
        "sector",
        "metadata_json",
        "created_at",
        "updated_at",
    },
    "market_bars": {
        "id",
        "asset_id",
        "ts",
        "timeframe",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source",
        "ingestion_run_id",
    },
    "lob_snapshots": {
        "id",
        "asset_id",
        "ts",
        "bid_levels_json",
        "ask_levels_json",
        "spread",
        "imbalance",
        "source",
    },
    "features": {
        "id",
        "asset_id",
        "ts",
        "feature_set",
        "values_json",
        "version",
    },
    "feature_runs": {
        "id",
        "feature_set",
        "version",
        "input_uri",
        "output_uri",
        "config_json",
        "rows",
        "columns",
        "started_at",
        "finished_at",
        "status",
        "error_json",
    },
    "signals": {
        "id",
        "asset_id",
        "ts",
        "model_name",
        "model_version",
        "horizon",
        "signal",
        "confidence",
        "explanation_json",
    },
    "backtest_runs": {
        "id",
        "name",
        "config_json",
        "metrics_json",
        "created_at",
    },
    "risk_runs": {
        "id",
        "universe",
        "config_json",
        "metrics_json",
        "created_at",
    },
    "model_artifacts": {
        "id",
        "model_name",
        "model_version",
        "artifact_uri",
        "metadata_json",
        "created_at",
    },
    "ingestion_runs": {
        "id",
        "source",
        "asset_type",
        "symbol",
        "timeframe",
        "start_ts",
        "end_ts",
        "status",
        "rows_written",
        "rows_deduplicated",
        "missing_ratio",
        "output_uri",
        "content_hash",
        "started_at",
        "finished_at",
        "error_json",
        "stats_json",
        "error",
    },
}
