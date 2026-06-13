"""Tests for the DuckDB analytical warehouse layer."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from src.warehouse.duckdb_context import (
    DuckDBWarehouseContext,
    default_dataset_globs,
)
from src.warehouse.materialize import build_research_panel, research_panel_sql


class WarehouseSqlTests(unittest.TestCase):
    """Warehouse SQL helpers should be deterministic and portable."""

    def test_default_globs_include_requested_data_lake_layout(self) -> None:
        globs = default_dataset_globs(Path("data/lake"))

        self.assertIn("data/lake/raw/**/*.parquet", globs["market_bars"])
        self.assertIn("data/lake/features/**/*.parquet", globs["features"])
        self.assertIn("data/lake/predictions/**/*.parquet", globs["predictions"])
        self.assertIn("data/lake/backtests/**/*.parquet", globs["backtests"])
        self.assertIn("data/lake/risk/**/*.parquet", globs["risk"])

    def test_research_panel_sql_filters_universe_dates_and_timeframe(self) -> None:
        sql = research_panel_sql(["SPY", "QQQ"], "2024-01-01", "2024-02-01", "1d")

        self.assertIn("from v_signal_panel", sql)
        self.assertIn("upper(symbol) in ('SPY', 'QQQ')", sql)
        self.assertIn("timeframe = '1d'", sql)
        self.assertIn("cast('2024-01-01' as timestamp)", sql)


@unittest.skipUnless(
    importlib.util.find_spec("duckdb") and importlib.util.find_spec("pyarrow"),
    "duckdb and pyarrow are required for local Parquet integration test",
)
class WarehouseDuckDBIntegrationTests(unittest.TestCase):
    """DuckDB should scan local Parquet without pandas materialization."""

    def test_build_research_panel_from_local_partitioned_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "data" / "lake"
            _write_market_bar_fixture(root)
            context = DuckDBWarehouseContext(root / "analytics.duckdb", root)

            try:
                result = build_research_panel(
                    ["SPY"],
                    "2024-01-01",
                    "2024-01-03",
                    "1d",
                    context=context,
                    output_path=root / "gold" / "panel.parquet",
                )
            finally:
                context.close()

            self.assertEqual(result.row_count, 2)
            self.assertTrue(result.output_path.exists())
            rows = _read_parquet_rows(result.output_path)
            self.assertEqual([row["symbol"] for row in rows], ["SPY", "SPY"])
            self.assertAlmostEqual(rows[1]["simple_return"], 0.01)


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
        {
            "ts": datetime(2024, 1, 1, tzinfo=UTC),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
            "source": "fixture",
        },
        {
            "ts": datetime(2024, 1, 2, tzinfo=UTC),
            "open": 100.0,
            "high": 102.0,
            "low": 100.0,
            "close": 101.0,
            "volume": 1100.0,
            "source": "fixture",
        },
    ]
    pq.write_table(pa.Table.from_pylist(rows), path)


def _read_parquet_rows(path: Path) -> list[dict[str, object]]:
    import pyarrow.parquet as pq

    return list(pq.ParquetFile(path).read().to_pylist())
