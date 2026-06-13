"""Tests for Phase 8 testing, validation, and backtesting."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.pipeline.evaluation import (
    compute_risk_report,
    evaluate_predictions,
    run_backtest_from_config,
    run_evaluation,
    run_simple_backtest,
)
from src.pipeline.evaluation.evaluator import feature_drift, prediction_drift
from src.pipeline.ingestion.validators import rows_to_parquet_bytes
from src.pipeline.training import train_model
from src.providers.registry import build_provider_registry


class Phase8EvaluationPipelineTests(unittest.TestCase):
    """Integration tests for Phase 8 evaluation outputs and persistence."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.previous_env = {
            "DATA_LAKE_ROOT": os.environ.get("DATA_LAKE_ROOT"),
            "SQLITE_PATH": os.environ.get("SQLITE_PATH"),
        }
        self.lake_root = Path(self.tmpdir) / "lake"
        self.sqlite_path = Path(self.tmpdir) / "db.sqlite3"
        os.environ["DATA_LAKE_ROOT"] = str(self.lake_root)
        os.environ["SQLITE_PATH"] = str(self.sqlite_path)
        self.registry = build_provider_registry(load_runtime_settings())
        self.dataset_root = self.lake_root / "datasets"
        self.model_root = self.lake_root / "models"
        self.report_root = self.lake_root / "reports" / "evaluation"
        self.window_dir = self.dataset_root / "dataset=test_eval" / "version=v1" / "window_id=0"
        self.window_dir.mkdir(parents=True, exist_ok=True)
        self._write_window_dataset()
        self._train_window_model()

    def tearDown(self) -> None:
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_evaluation_writes_predictions_reports_and_metrics(self) -> None:
        config = self._evaluation_config()
        result = run_evaluation(config, self.registry)

        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(len(result.windows), 1)
        window = result.windows[0]
        prediction_path = self.lake_root / str(window.prediction_output["output_path"])
        self.assertTrue(prediction_path.exists())
        self.assertTrue(Path(window.reports["json"]).exists())
        self.assertTrue(Path(window.reports["markdown"]).exists())
        self.assertTrue(Path(result.reports["json"]).exists())
        self.assertTrue(Path(result.reports["markdown"]).exists())
        self.assertIn("aggregate_metrics", result.aggregate_report)
        self.assertIn("model_not_better_than_baseline", result.aggregate_report)
        self.assertIn("baseline_metrics", window.metrics)
        self.assertIn("model_metrics", window.metrics)
        self.assertGreater(self._db_count("backtest_runs"), 0)

    def test_backtest_from_config_reads_saved_predictions(self) -> None:
        result = run_evaluation(self._evaluation_config(), self.registry)
        prediction_path = self.lake_root / str(result.windows[0].prediction_output["output_path"])
        backtest = run_backtest_from_config(
            {
                "name": "phase8_direct_backtest",
                "predictions_path": str(prediction_path),
                "signal_threshold": 0.0,
                "require_duckdb": False,
            },
            self.registry,
        )
        self.assertEqual(backtest["status"], "COMPLETED")
        self.assertIn("cumulative_return", backtest["metrics"])
        self.assertGreater(self._db_count("backtest_runs"), 0)

    def test_model_vs_naive_baseline_warning_is_reported(self) -> None:
        comparison = evaluate_predictions(
            [
                {"y_true": 1.0, "y_pred": 0.0},
                {"y_true": 1.0, "y_pred": 0.0},
            ],
            [
                {"y_true": 1.0, "y_pred": 1.0},
                {"y_true": 1.0, "y_pred": 1.0},
            ],
        )
        self.assertFalse(comparison.model_better_than_baseline)
        self.assertEqual(comparison.warning, "model_not_better_than_naive_baseline")

    def test_backtest_and_risk_reports_are_json_safe(self) -> None:
        rows = [
            {"signal": 1.0, "y_true": 0.01},
            {"signal": -1.0, "y_true": -0.02},
            {"signal": 1.0, "y_true": -0.01},
        ]
        backtest = run_simple_backtest(rows).to_dict()
        risk = compute_risk_report(rows).to_dict()
        self.assertIn("sharpe_like", backtest)
        self.assertIn("max_drawdown", risk)
        json.dumps(backtest | risk)

    def test_feature_and_prediction_drift(self) -> None:
        train_rows = [{"feature": 1.0}, {"feature": 2.0}]
        eval_rows = [{"feature": 3.0}, {"feature": 4.0}]
        predictions = [{"y_pred": 1.0}, {"y_pred": 2.0}, {"y_pred": 4.0}, {"y_pred": 5.0}]
        self.assertEqual(feature_drift(train_rows, eval_rows)["feature"], 2.0)
        self.assertGreater(prediction_drift(predictions)["mean_shift"], 0.0)

    def _write_window_dataset(self) -> None:
        train_rows = [
            {"symbol": "SPY", "ts": "2020-01-01T00:00:00+00:00", "feature": 1.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-02T00:00:00+00:00", "feature": 2.0, "target": 0.02},
            {"symbol": "SPY", "ts": "2020-01-03T00:00:00+00:00", "feature": 3.0, "target": 0.03},
        ]
        validation_rows = [
            {"symbol": "SPY", "ts": "2020-01-04T00:00:00+00:00", "feature": 4.0, "target": 0.04},
            {"symbol": "SPY", "ts": "2020-01-05T00:00:00+00:00", "feature": 5.0, "target": 0.05},
        ]
        test_rows = [
            {"symbol": "SPY", "ts": "2020-01-06T00:00:00+00:00", "feature": 6.0, "target": 0.06},
            {"symbol": "SPY", "ts": "2020-01-07T00:00:00+00:00", "feature": 7.0, "target": 0.07},
        ]
        (self.window_dir / "train.parquet").write_bytes(rows_to_parquet_bytes(train_rows))
        (self.window_dir / "validation.parquet").write_bytes(rows_to_parquet_bytes(validation_rows))
        (self.window_dir / "test.parquet").write_bytes(rows_to_parquet_bytes(test_rows))

    def _train_window_model(self) -> None:
        train_rows, validation_rows = self._rows()
        train_model(
            model_name="ridge_return",
            train_rows=train_rows,
            val_rows=validation_rows,
            config={"target_column": "target", "feature_columns": ["feature"], "seed": 42},
            output_dir=self.model_root / "ridge_return" / "window_0",
        )

    def _rows(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        train_rows = [
            {"symbol": "SPY", "ts": "2020-01-01T00:00:00+00:00", "feature": 1.0, "target": 0.01},
            {"symbol": "SPY", "ts": "2020-01-02T00:00:00+00:00", "feature": 2.0, "target": 0.02},
            {"symbol": "SPY", "ts": "2020-01-03T00:00:00+00:00", "feature": 3.0, "target": 0.03},
        ]
        validation_rows = [
            {"symbol": "SPY", "ts": "2020-01-04T00:00:00+00:00", "feature": 4.0, "target": 0.04},
            {"symbol": "SPY", "ts": "2020-01-05T00:00:00+00:00", "feature": 5.0, "target": 0.05},
        ]
        return train_rows, validation_rows

    def _evaluation_config(self) -> dict[str, object]:
        return {
            "name": "phase8_eval_test",
            "model_name": "ridge_return",
            "model_version": "phase8_test",
            "dataset_name": "test_eval",
            "dataset_version": "v1",
            "dataset_path": str(self.dataset_root),
            "model_root": str(self.model_root),
            "report_root": str(self.report_root),
            "prediction_root": "predictions",
            "target_column": "target",
            "horizon": "1d",
            "require_duckdb": False,
            "store_metrics": True,
        }

    def _db_count(self, table: str) -> int:
        with sqlite3.connect(self.sqlite_path) as connection:
            try:
                return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.OperationalError:
                return 0


if __name__ == "__main__":
    unittest.main()
