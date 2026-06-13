"""Phase 4 deterministic preprocessing pipeline tests."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

from src.cli import main
from src.config.settings import load_runtime_settings
from src.pipeline.ingestion.source_base import read_local_rows
from src.pipeline.ingestion.validators import rows_to_parquet_bytes
from src.pipeline.preprocessing import run_preprocessing
from src.providers.registry import build_provider_registry


class Phase4PreprocessingPipelineTests(unittest.TestCase):
    """Preprocessing should be deterministic and leakage-safe."""

    def test_preprocessing_outputs_bronze_silver_and_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_raw_rows(root, _raw_rows())
            registry = _registry(root)
            config = _config(root)

            first = run_preprocessing(config, registry).to_dict()
            second = run_preprocessing(config, registry).to_dict()
            silver_rows = read_local_rows(root / "lake" / second["silver_path"])
            report_path = root / "lake" / second["quality_report_path"]
            stored_report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertEqual(first["quality_report"], second["quality_report"])
        self.assertEqual(first["quality_report"], stored_report)
        self.assertEqual(second["duplicates_removed"], 1)
        self.assertEqual(second["bronze_rows"], 2)
        self.assertEqual(second["silver_rows"], 3)
        self.assertEqual([row["ts"] for row in silver_rows], sorted(row["ts"] for row in silver_rows))
        self.assertTrue(any(row["imputed"] for row in silver_rows))
        self.assertTrue(any(row["missing_ohlcv"] for row in silver_rows))
        self.assertTrue(any(row["zero_volume"] for row in silver_rows))
        self.assertTrue(any(row["price_jump"] for row in silver_rows))
        self.assertTrue(any(row["timezone_adjusted"] for row in silver_rows))
        self.assertTrue(stored_report["no_future_leakage"])
        self.assertEqual(stored_report["timestamp_alignment"]["timezone"], "UTC")
        self.assertEqual(stored_report["timestamp_alignment"]["calendar"]["inserted_rows"], 1)
        self.assertEqual(
            stored_report["missing_value_policy"],
            "previous_observation_only_no_future_leakage",
        )

    def test_cli_preprocess_run_uses_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_raw_rows(root, _raw_rows())
            config_path = root / "preprocess.json"
            config_path.write_text(json.dumps(_config(root)), encoding="utf-8")

            with _local_env(root):
                payload = _json_cli(["preprocess", "run", "--config", str(config_path)])
            silver_uri = str(payload["quality_report"]["outputs"]["silver"]["uri"])
            silver_exists = Path(urlparse(silver_uri).path).exists()

        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["silver_rows"], 3)
        self.assertIn("quality", payload["quality_report"])
        self.assertTrue(silver_exists)


def _write_raw_rows(root: Path, rows: list[dict[str, object]]) -> Path:
    path = (
        root
        / "lake"
        / "raw"
        / "source=unit"
        / "asset_type=equity"
        / "symbol=SPY"
        / "timeframe=1d"
        / "date=2024-01-01"
        / "part-000.parquet"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rows_to_parquet_bytes(rows))
    return path


def _raw_rows() -> list[dict[str, object]]:
    return [
        {
            "symbol": "SPY",
            "ts": "2024-01-01T09:30:00-05:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
            "source": "unit",
        },
        {
            "symbol": "SPY",
            "ts": "2024-01-01T09:30:00-05:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
            "source": "unit",
        },
        {
            "symbol": "SPY",
            "ts": "2024-01-03T09:30:00-05:00",
            "open": 200.0,
            "high": None,
            "low": 199.0,
            "close": 200.0,
            "volume": 0.0,
            "source": "unit",
        },
    ]


def _config(root: Path) -> dict[str, object]:
    return {
        "lake_root": str(root / "lake"),
        "raw_path": str(root / "lake" / "raw"),
        "bronze_path": "bronze/market_bars/part-000.parquet",
        "silver_path": "silver/market_bars/part-000.parquet",
        "quality_report_path": "silver/market_bars/_quality_report.json",
        "calendar_frequency": "1d",
        "price_jump_threshold": 0.2,
        "stale_periods": 1,
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
