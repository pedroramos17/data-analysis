"""Phase 5 feature extraction pipeline tests."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.cli import main
from src.config.settings import load_runtime_settings
from src.pipeline.features import run_feature_pipeline
from src.pipeline.ingestion.source_base import read_local_rows
from src.pipeline.ingestion.validators import rows_to_parquet_bytes
from src.providers.registry import build_provider_registry


class Phase5FeaturePipelineTests(unittest.TestCase):
    """Feature extraction should be versioned, deterministic, and leakage-safe."""

    def test_feature_pipeline_writes_versioned_outputs_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_silver_rows(root, _silver_rows())
            registry = _registry(root)
            config = _config(root)

            first = run_feature_pipeline(config, registry).to_dict()
            second = run_feature_pipeline(config, registry).to_dict()
            price_path = _output_path(root, "price_volume", "phase5_test", "SPY", "1d")
            price_exists = price_path.exists()
            price_rows = read_local_rows(price_path)
            feature_run_rows = _feature_run_rows(root / "db.sqlite3")

        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertEqual(first["rows"], second["rows"])
        self.assertEqual(first["feature_sets"], ["price_volume", "lob", "multifractal", "regime", "risk", "graph"])
        self.assertTrue(first["no_future_leakage"])
        self.assertIn("past_and_current", first["rolling_window_policy"])
        self.assertGreater(first["runtime"]["runtime_seconds"], 0)
        self.assertGreater(first["runtime"]["row_throughput_per_second"], 0)
        self.assertTrue(price_exists)
        self.assertEqual({row["version"] for row in price_rows}, {"phase5_test"})
        self.assertAlmostEqual(price_rows[1]["simple_return"], 0.01)
        self.assertIsNone(price_rows[0]["simple_return"])
        self.assertIn("rolling_volatility", price_rows[2])
        self.assertTrue(any("feature_set=price_volume/version=phase5_test" in output["path"] for output in first["outputs"]))
        self.assertEqual(len(feature_run_rows), len(first["outputs"]))
        self.assertEqual({row["status"] for row in feature_run_rows}, {"COMPLETED"})

    def test_cli_features_build_runs_phase5_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_silver_rows(root, _silver_rows())
            config_path = root / "features.json"
            config_path.write_text(json.dumps(_config(root)), encoding="utf-8")

            with _local_env(root):
                payload = _json_cli(["features", "build", "--config", str(config_path)])

        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["version"], "phase5_test")
        self.assertIn("runtime", payload)
        self.assertGreater(payload["metadata_rows"], 0)


def _write_silver_rows(root: Path, rows: list[dict[str, object]]) -> Path:
    path = root / "lake" / "silver" / "market_bars" / "part-000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rows_to_parquet_bytes(rows))
    return path


def _silver_rows() -> list[dict[str, object]]:
    return [
        _row("2024-01-01T00:00:00+00:00", 100.0, 1000.0, 99.99, 100.01, 100.0, 110.0),
        _row("2024-01-02T00:00:00+00:00", 101.0, 1100.0, 100.99, 101.01, 120.0, 100.0),
        _row("2024-01-03T00:00:00+00:00", 102.0, 900.0, 101.99, 102.01, 130.0, 90.0),
        _row("2024-01-04T00:00:00+00:00", 103.0, 950.0, 102.99, 103.01, 140.0, 80.0),
    ]


def _row(
    ts: str,
    close: float,
    volume: float,
    bid: float,
    ask: float,
    bid_size: float,
    ask_size: float,
) -> dict[str, object]:
    return {
        "symbol": "SPY",
        "asset_type": "equity",
        "timeframe": "1d",
        "ts": ts,
        "open": close - 0.5,
        "high": close + 0.5,
        "low": close - 1.0,
        "close": close,
        "volume": volume,
        "bid_price_1": bid,
        "ask_price_1": ask,
        "bid_size_1": bid_size,
        "ask_size_1": ask_size,
        "source": "unit",
    }


def _config(root: Path) -> dict[str, object]:
    return {
        "lake_root": str(root / "lake"),
        "input_path": str(root / "lake" / "silver" / "market_bars"),
        "version": "phase5_test",
        "groups": ["price_volume", "lob", "multifractal", "regime", "risk", "graph"],
        "universe": ["SPY"],
        "timeframe": "1d",
        "rolling_window": 3,
        "long_window": 4,
    }


def _registry(root: Path):
    settings = load_runtime_settings(
        env={
            "DATA_LAKE_ROOT": str(root / "lake"),
            "SQLITE_PATH": str(root / "db.sqlite3"),
            "MODEL_CACHE_DIR": str(root / "models"),
        },
        base_dir=root,
    )
    return build_provider_registry(settings)


def _output_path(root: Path, feature_set: str, version: str, symbol: str, timeframe: str) -> Path:
    return (
        root
        / "lake"
        / "features"
        / f"feature_set={feature_set}"
        / f"version={version}"
        / f"symbol={symbol}"
        / f"timeframe={timeframe}"
        / "part-000.parquet"
    )


def _feature_run_rows(db_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT feature_set, version, rows, columns, status FROM feature_runs ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def _json_cli(argv: list[str]) -> dict[str, object]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = main(argv)
    if code != 0:
        raise AssertionError(f"CLI exited with {code}: {stdout.getvalue()}")
    return json.loads(stdout.getvalue())


def _local_env(root: Path):
    return patch.dict(
        os.environ,
        {
            "APP_ENV": "local",
            "DEPLOYMENT_MODE": "onprem",
            "DB_MODE": "sqlite",
            "SQLITE_PATH": str(root / "db.sqlite3"),
            "STORAGE_PROVIDER": "local",
            "DATA_LAKE_ROOT": str(root / "lake"),
            "QUEUE_PROVIDER": "local",
            "COMPUTE_PROVIDER": "local",
            "MODEL_CACHE_DIR": str(root / "models"),
        },
        clear=True,
    )


if __name__ == "__main__":
    unittest.main()
