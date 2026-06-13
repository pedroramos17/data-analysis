"""Tests for the Phase 13 MVP demo workflow."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.cli import main
from src.models.base import ForecastPrediction
from src.models.inference.batch_predict import PredictionBatchResult
from src.workflows.mvp_demo import (
    MVP_STEPS,
    MvpDemoConfig,
    MvpDemoResult,
    MvpStepResult,
    _backtest_report,
    run_mvp_demo,
    sample_market_rows,
)

HAVE_E2E_DEPS = all(
    importlib.util.find_spec(name) for name in ("sqlalchemy", "duckdb", "pyarrow")
)


class MvpDemoUnitTests(unittest.TestCase):
    """Dependency-light workflow behavior should stay deterministic."""

    def test_config_parses_cli_friendly_values(self) -> None:
        config = MvpDemoConfig.from_mapping(
            {
                "run_id": "unit",
                "symbols": "SPY, QQQ",
                "periods": "5",
                "optional_sequence_models": "fin_mamba_small,samba_small",
                "lake_root": "data/lake",
                "duckdb_path": "data/lake/analytics.duckdb",
                "persist_feature_metadata": "false",
            }
        )

        self.assertEqual(config.run_id, "unit")
        self.assertEqual(config.symbols, ("SPY", "QQQ"))
        self.assertEqual(config.periods, 5)
        self.assertEqual(
            config.optional_sequence_models,
            ("fin_mamba_small", "samba_small"),
        )
        self.assertEqual(config.lake_root, Path("data/lake"))
        self.assertFalse(config.persist_feature_metadata)

    def test_sample_market_rows_are_deterministic(self) -> None:
        rows = sample_market_rows(
            MvpDemoConfig(symbols=("SPY",), periods=3, start="2024-01-01")
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["symbol"], "SPY")
        self.assertEqual(rows[0]["timeframe"], "1d")
        self.assertGreater(float(rows[-1]["close"]), 0.0)
        self.assertIn("log_return", rows[-1])

    def test_cli_mvp_demo_prints_workflow_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_path = _write_json(root / "mvp.json", {"run_id": "unit"})
            result = MvpDemoResult(
                "unit",
                "COMPLETED",
                (MvpStepResult("export_report_json", "COMPLETED", {"path": "x"}),),
                "logs/log=mvp_demo/date=2024-01-01/unit_report.json",
                "file:///tmp/unit_report.json",
            )

            with _local_env(root):
                with patch("src.cli.run_mvp_demo", return_value=result) as runner:
                    code, stdout, stderr = _run_cli(
                        ["mvp-demo", "--config", str(config_path)]
                    )

        payload = json.loads(stdout)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["run_id"], "unit")
        self.assertEqual(payload["status"], "COMPLETED")
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args[0]["run_id"], "unit")

    def test_backtest_report_includes_alpha_validation(self) -> None:
        config = MvpDemoConfig(symbols=("SPY",), periods=2)
        rows = sample_market_rows(config)
        prediction_result = PredictionBatchResult(
            predictions=[
                ForecastPrediction("SPY", "2024-01-02", "1d", 0.01, 0.01),
            ],
            explanations={},
        )

        report = _backtest_report(config, rows, prediction_result)

        self.assertIn("alpha_validation", report)
        self.assertIn("ic", report["alpha_validation"])
        self.assertIn("melao_index_placeholder", report["alpha_validation"])


@unittest.skipUnless(
    HAVE_E2E_DEPS,
    "SQLAlchemy, DuckDB, and PyArrow are required for the MVP demo integration",
)
class MvpDemoIntegrationTests(unittest.TestCase):
    """The full local pipeline should complete when optional deps are installed."""

    def test_run_mvp_demo_local_provider_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            lake_root = root / "lake"
            database_url = f"sqlite:///{(root / 'mvp.sqlite3').as_posix()}"
            config = MvpDemoConfig(
                run_id="unit_mvp",
                symbols=("SPY",),
                periods=6,
                lake_root=lake_root,
                duckdb_path=lake_root / "analytics.duckdb",
                database_url=database_url,
                optional_sequence_models=(),
            )

            with _local_env(root):
                result = run_mvp_demo(config)

            report_path = lake_root / result.report_path
            self.assertEqual(result.status, "COMPLETED")
            self.assertEqual([step.name for step in result.steps], list(MVP_STEPS))
            self.assertTrue(report_path.exists())


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _local_env(base_dir: Path):
    return patch.dict(
        "os.environ",
        {
            "APP_ENV": "local",
            "DEPLOYMENT_MODE": "onprem",
            "DB_MODE": "sqlite",
            "SQLITE_PATH": str(base_dir / "db.sqlite3"),
            "DATA_LAKE_ROOT": str(base_dir / "lake"),
            "DUCKDB_PATH": str(base_dir / "lake" / "analytics.duckdb"),
            "STORAGE_PROVIDER": "local",
            "QUEUE_PROVIDER": "local",
            "MODEL_PROVIDER": "local",
            "MODEL_CACHE_DIR": str(base_dir / "models"),
            "COMPUTE_PROVIDER": "local",
        },
        clear=True,
    )


if __name__ == "__main__":
    unittest.main()
