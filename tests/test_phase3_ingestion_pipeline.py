"""Phase 3 idempotent ingestion pipeline tests."""

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
from src.pipeline.ingestion import run_ingestion, validate_ingestion_path
from src.providers.registry import build_provider_registry


class Phase3IngestionPipelineTests(unittest.TestCase):
    """Ingestion should be repeatable, local-first, and metadata-backed."""

    def test_repeatable_ingestion_deduplicates_and_records_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = _registry(root)
            config = _market_config(_duplicate_rows())

            first = run_ingestion(config, registry).to_dict()
            second = run_ingestion(config, registry).to_dict()

            rows = _ingestion_rows(root / "db.sqlite3")
            output_path = root / "lake" / str(second["runs"][0]["stats_json"]["object_path"])
            validation = validate_ingestion_path(output_path.parent)

        self.assertEqual(first["status"], "COMPLETED")
        self.assertEqual(second["status"], "COMPLETED")
        self.assertEqual(first["runs"][0]["content_hash"], second["runs"][0]["content_hash"])
        self.assertEqual(first["rows_written"], 1)
        self.assertEqual(first["rows_deduplicated"], 1)
        self.assertIn("raw/source=mock_csv/asset_type=equity/symbol=SPY", str(output_path))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "COMPLETED")
        self.assertEqual(rows[0]["rows_written"], 1)
        self.assertEqual(rows[0]["rows_deduplicated"], 1)
        self.assertEqual(validation["status"], "VALID")
        self.assertEqual(validation["rows"], 1)

    def test_failed_ingestion_records_error_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = _registry(root)
            result = run_ingestion(_market_config([_bad_row()]), registry).to_dict()
            rows = _ingestion_rows(root / "db.sqlite3")

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["runs"][0]["status"], "FAILED")
        self.assertIn("close", result["runs"][0]["error_json"]["message"])
        self.assertEqual(rows[0]["status"], "FAILED")
        self.assertIn("IngestionValidationError", rows[0]["error_json"])

    def test_cli_ingest_run_and_validate_use_local_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = root / "ingest.json"
            config_path.write_text(json.dumps(_market_config(_duplicate_rows())), encoding="utf-8")

            with _local_env(root):
                run_payload = _json_cli(["ingest", "run", "--config", str(config_path)])
                object_path = root / "lake" / str(run_payload["runs"][0]["stats_json"]["object_path"])
                validate_payload = _json_cli(["ingest", "validate", "--path", str(object_path.parent)])

        self.assertEqual(run_payload["status"], "COMPLETED")
        self.assertEqual(run_payload["rows_written"], 1)
        self.assertEqual(validate_payload["status"], "VALID")
        self.assertEqual(validate_payload["rows"], 1)


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


def _market_config(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "source": "mock_csv",
        "source_type": "market",
        "asset_type": "equity",
        "timeframe": "1d",
        "symbols": ["SPY"],
        "rows": rows,
    }


def _duplicate_rows() -> list[dict[str, object]]:
    row = {
        "symbol": "SPY",
        "ts": "2024-01-01T09:30:00-05:00",
        "open": "100.0",
        "high": "101.0",
        "low": "99.5",
        "close": "100.5",
        "volume": "1000",
        "note": "",
    }
    return [dict(row), dict(row)]


def _bad_row() -> dict[str, object]:
    return {
        "symbol": "SPY",
        "ts": "2024-01-01T09:30:00Z",
        "open": 100.0,
        "high": 101.0,
        "low": 99.5,
        "volume": 1000,
    }


def _ingestion_rows(db_path: Path) -> list[dict[str, object]]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT status, rows_written, rows_deduplicated, content_hash, error_json "
            "FROM ingestion_runs ORDER BY id"
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
