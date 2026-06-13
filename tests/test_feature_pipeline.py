"""Tests for the Phase 10 feature pipeline."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from src.features.definitions import FEATURE_GROUPS, feature_names
from src.features.metadata import feature_metadata_records, persist_feature_metadata
from src.features.pipeline import (
    FeaturePipelineConfig,
    build_feature_store,
    versioned_feature_output_path,
)
from src.features.sql import feature_store_sql


class FeaturePipelineSqlTests(unittest.TestCase):
    """Feature catalog and SQL generation should be deterministic."""

    def test_catalog_covers_requested_feature_groups(self) -> None:
        names = set(feature_names())

        self.assertEqual(
            set(FEATURE_GROUPS),
            {
                "price_volume",
                "lob",
                "multifractal",
                "risk",
                "portfolio",
                "regime",
                "knowledge_graph",
            },
        )
        for expected in (
            "returns",
            "log_returns",
            "rolling_volatility",
            "realized_volatility",
            "microprice",
            "generalized_hurst_exponent",
            "mf_dfa_features",
            "var",
            "cvar",
            "mean_variance_baseline",
            "risk_parity_baseline",
            "volatility_regime",
            "graph_embeddings_placeholder",
        ):
            self.assertIn(expected, names)

    def test_feature_store_sql_filters_and_versions_outputs(self) -> None:
        sql = feature_store_sql(
            version="unit_v1",
            groups=("price_volume", "risk", "knowledge_graph"),
            universe=("SPY", "QQQ"),
            start="2024-01-01",
            end="2024-02-01",
            timeframe="1d",
        )

        self.assertIn("from v_market_bars", sql)
        self.assertIn("upper(symbol) in ('SPY', 'QQQ')", sql)
        self.assertIn("timeframe = '1d'", sql)
        self.assertIn("'unit_v1' as version", sql)
        self.assertIn("'returns' as feature_name", sql)
        self.assertIn("'rolling_beta' as feature_name", sql)
        self.assertIn("'graph_embeddings_placeholder' as feature_name", sql)
        self.assertIn("order by symbol, ts, feature_set, feature_name", sql)

    def test_invalid_group_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "not_a_group"):
            feature_store_sql(version="x", groups=("not_a_group",))

    def test_default_output_path_is_versioned_under_gold_features(self) -> None:
        path = versioned_feature_output_path(Path("data/lake"), "phase10_v1")

        self.assertEqual(
            path,
            Path("data/lake/gold/features/version=phase10_v1/feature_store.parquet"),
        )

    def test_config_parses_groups_and_metadata_options(self) -> None:
        config = FeaturePipelineConfig.from_mapping(
            {
                "version": "v2",
                "groups": "price_volume,risk",
                "universe": ["SPY"],
                "persist_metadata": "true",
                "database_url": "sqlite:///features.db",
            }
        )

        self.assertEqual(config.version, "v2")
        self.assertEqual(config.groups, ("price_volume", "risk"))
        self.assertEqual(config.universe, ("SPY",))
        self.assertTrue(config.persist_metadata)
        self.assertEqual(config.database_url, "sqlite:///features.db")

    def test_metadata_records_aggregate_long_feature_rows(self) -> None:
        rows = [
            _feature_row("SPY", "price_volume", "returns", 0.01),
            _feature_row("SPY", "price_volume", "log_returns", 0.00995),
            _feature_row("SPY", "risk", "var", -0.02),
        ]

        records = feature_metadata_records(rows)

        self.assertEqual(len(records), 2)
        price_record = next(row for row in records if row.feature_set == "price_volume")
        self.assertEqual(price_record.values_json["returns"], 0.01)
        self.assertEqual(price_record.values_json["log_returns"], 0.00995)


@unittest.skipUnless(
    importlib.util.find_spec("sqlalchemy"),
    "SQLAlchemy is required for compatibility metadata persistence",
)
class FeatureMetadataPersistenceTests(unittest.TestCase):
    """Feature metadata should persist into the compatibility schema."""

    def test_persist_feature_metadata_to_sqlite(self) -> None:
        from sqlalchemy import create_engine, select

        from src.database.core_schema import features

        with tempfile.TemporaryDirectory() as temp_dir:
            database_url = f"sqlite:///{Path(temp_dir, 'features.sqlite').as_posix()}"

            count = persist_feature_metadata(
                database_url,
                [
                    _feature_row("SPY", "price_volume", "returns", 0.01),
                    _feature_row("SPY", "price_volume", "log_returns", 0.00995),
                ],
            )
            engine = create_engine(database_url)
            try:
                with engine.connect() as connection:
                    payload = connection.execute(select(features.c.values_json)).scalar_one()
            finally:
                engine.dispose()

        self.assertEqual(count, 1)
        self.assertEqual(payload["features"]["returns"], 0.01)
        self.assertEqual(payload["features"]["log_returns"], 0.00995)


@unittest.skipUnless(
    importlib.util.find_spec("duckdb") and importlib.util.find_spec("pyarrow"),
    "duckdb and pyarrow are required for feature-store integration test",
)
class FeaturePipelineDuckDBIntegrationTests(unittest.TestCase):
    """Feature pipeline should materialize DuckDB/Parquet feature rows."""

    def test_build_feature_store_from_market_bar_parquet(self) -> None:
        from src.warehouse.duckdb_context import DuckDBWarehouseContext

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data" / "lake"
            _write_market_bar_fixture(root)
            context = DuckDBWarehouseContext(root / "analytics.duckdb", root)
            try:
                result = build_feature_store(
                    FeaturePipelineConfig(
                        version="unit_v1",
                        groups=("price_volume", "knowledge_graph"),
                        universe=("SPY",),
                        start="2024-01-01",
                        end="2024-01-03",
                        timeframe="1d",
                        output_path=root / "gold" / "features" / "unit.parquet",
                    ),
                    context=context,
                )
            finally:
                context.close()

            rows = _read_parquet_rows(result.output_path)

        self.assertGreater(result.row_count, 0)
        self.assertTrue(result.output_path.exists())
        self.assertIn("returns", {row["feature_name"] for row in rows})
        self.assertIn("unit_v1", {row["version"] for row in rows})


def _feature_row(
    symbol: str,
    feature_set: str,
    feature_name: str,
    feature_value: float,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "asset_type": "equity",
        "ts": datetime(2024, 1, 2, tzinfo=UTC),
        "timeframe": "1d",
        "feature_set": feature_set,
        "version": "unit_v1",
        "feature_name": feature_name,
        "feature_value": feature_value,
        "source": "unit-test",
    }


def _write_market_bar_fixture(root: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = (
        root
        / "raw"
        / "source=yahoo"
        / "asset_type=equity"
        / "symbol=SPY"
        / "timeframe=1d"
        / "date=2024-01-01"
        / "part-000.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"ts": datetime(2024, 1, 1, tzinfo=UTC), "close": 100.0, "volume": 1000.0},
        {"ts": datetime(2024, 1, 2, tzinfo=UTC), "close": 101.0, "volume": 1100.0},
        {"ts": datetime(2024, 1, 3, tzinfo=UTC), "close": 102.0, "volume": 900.0},
    ]
    pq.write_table(pa.Table.from_pylist(rows), path)


def _read_parquet_rows(path: Path) -> list[dict[str, object]]:
    import pyarrow.parquet as pq

    return list(pq.ParquetFile(path).read().to_pylist())


if __name__ == "__main__":
    unittest.main()
