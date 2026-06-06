"""Smoke tests for the Phase 12 CLI command surface."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.cli import main
from src.config.settings import load_runtime_settings
from src.orchestration.state import PipelineStateStore


class CliSmokeTests(unittest.TestCase):
    """Core MVP commands should run without the API server."""

    def test_config_show_and_smoke_test(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with _local_env(Path(temp_dir)):
                config_code, config_stdout, _ = _run_cli(["config", "show"])
                smoke_code, smoke_stdout, _ = _run_cli(["smoke-test"])

        config = json.loads(config_stdout)
        smoke = json.loads(smoke_stdout)
        self.assertEqual(config_code, 0)
        self.assertEqual(config["database"]["provider"], "sqlite")
        self.assertEqual(smoke_code, 0)
        self.assertTrue(smoke["db"]["ok"])
        self.assertTrue(smoke["queue"]["ok"])
        self.assertIn("naive_return", smoke["models"])

    def test_db_migrate_runs_local_provider_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with _local_env(Path(temp_dir)):
                code, stdout, _ = _run_cli(["db", "migrate"])

        payload = json.loads(stdout)
        self.assertEqual(code, 0)
        self.assertEqual(payload["database"]["provider"], "sqlite")
        self.assertIn(payload["compatibility_schema"]["status"], {"ok", "skipped"})

    def test_ingest_runs_locally_and_manifest_jobs_queue_without_api_server(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ingest_config = _write_json(root / "ingest.json", {"source": "sample"})
            backtest_config = _write_json(root / "backtest.json", {"name": "smoke"})
            risk_config = _write_json(root / "risk.json", {"name": "smoke"})

            with _local_env(root):
                ingest = _json_cli(["ingest", "run", "--config", str(ingest_config)])
                backtest = _json_cli(["backtest", "run", "--config", str(backtest_config)])
                risk = _json_cli(["risk", "run", "--config", str(risk_config)])

        self.assertEqual(ingest["status"], "COMPLETED")
        self.assertGreaterEqual(ingest["rows_written"], 1)
        self.assertEqual(backtest["status"], "PLANNED")
        self.assertEqual(risk["status"], "PLANNED")

    def test_feature_and_warehouse_commands_call_materializers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            feature_config = _write_json(root / "features.json", {"version": "v1"})
            panel_config = _write_json(root / "panel.json", {"universe": ["SPY"]})
            feature_result = SimpleNamespace(
                to_dict=lambda: {
                    "status": "COMPLETED",
                    "rows": 3,
                    "version": "v1",
                    "groups": ["price_volume"],
                    "metadata_rows": 1,
                }
            )
            panel_result = SimpleNamespace(
                output_path=root / "panel.parquet",
                row_count=2,
                source_view="v_signal_panel",
            )

            with _local_env(root):
                with patch("src.cli.run_feature_pipeline", return_value=feature_result):
                    features = _json_cli(["features", "build", "--config", str(feature_config)])
                with patch("src.cli.build_panel_from_config", return_value=panel_result):
                    panel = _json_cli(["warehouse", "build-panel", "--config", str(panel_config)])

        self.assertEqual(features["rows"], 3)
        self.assertEqual(features["version"], "v1")
        self.assertEqual(panel["rows"], 2)
        self.assertEqual(panel["source_view"], "v_signal_panel")

    def test_model_train_and_predict_run_small_sync_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            train_config = _write_json(
                root / "model.json",
                {
                    "model_name": "naive_return",
                    "dataset": [
                        {"symbol": "SPY", "ts": "2024-01-01", "log_return": 0.01},
                        {"symbol": "SPY", "ts": "2024-01-02", "log_return": 0.02},
                    ],
                    "output_path": str(root / "model.json.out"),
                },
            )
            predict_config = _write_json(
                root / "predict.json",
                {
                    "model_name": "naive_return",
                    "train_dataset": [
                        {"symbol": "SPY", "ts": "2024-01-01", "log_return": 0.01},
                        {"symbol": "SPY", "ts": "2024-01-02", "log_return": 0.02},
                    ],
                    "dataset": [{"symbol": "SPY", "ts": "2024-01-03"}],
                    "horizon": "1d",
                },
            )

            with _local_env(root):
                train = _json_cli(["model", "train", "--config", str(train_config)])
                predict = _json_cli(["model", "predict", "--config", str(predict_config)])

        self.assertEqual(train["status"], "COMPLETED")
        self.assertEqual(train["metadata"]["result"]["model"]["model_name"], "naive_return_baseline")
        self.assertEqual(predict["status"], "COMPLETED")
        self.assertEqual(predict["metadata"]["result"]["predictions"][0]["prediction"], 0.02)

    def test_gpu_job_dry_run_uses_python3_default_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output = root / "gpu_job.json"

            with _local_env(root):
                payload = _json_cli(["gpu-job-dry-run", "--output", str(output)])

            job_spec = payload["metadata"]["job_spec"]
            self.assertTrue(str(job_spec["command"]).startswith("python3 -m src.cli"))
            self.assertTrue(output.exists())

    def test_storage_sync_reports_missing_object_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with _local_env(Path(temp_dir)):
                code, _stdout, stderr = _run_cli(
                    ["storage", "sync", "--from", "local", "--to", "object"]
                )

        self.assertEqual(code, 1)
        self.assertIn("STORAGE_PROVIDER", stderr)
        self.assertIn("OBJECT_STORAGE_BUCKET", stderr)

    def test_efficiency_report_returns_persisted_report_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with _local_env(root):
                state = PipelineStateStore.from_settings(load_runtime_settings())
                run = state.create_run("persisted_report", {"name": "persisted_report"})
                state.update_run_status(
                    run.id,
                    "COMPLETED",
                    efficiency={
                        "report": {
                            "pipeline_run_id": run.id,
                            "summary": {"task_count": 1},
                            "quality_gates_passed": True,
                        },
                        "report_paths": {"json_path": "reports/efficiency/pipeline_run_1.json"},
                    },
                )

                payload = _json_cli(["efficiency", "report", "--run-id", str(run.id)])

        self.assertEqual(payload["run_id"], run.id)
        self.assertEqual(payload["status"], "COMPLETED")
        self.assertEqual(payload["report"]["summary"]["task_count"], 1)
        self.assertEqual(payload["report_paths"]["json_path"], "reports/efficiency/pipeline_run_1.json")

    def test_efficiency_report_regenerates_from_task_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with _local_env(root):
                state = PipelineStateStore.from_settings(load_runtime_settings())
                run = state.create_run(
                    "regenerate_report",
                    {
                        "name": "regenerate_report",
                        "efficiency_gates": {"min_rows_per_second": 10},
                    },
                )
                state.complete_task(
                    run.id,
                    "features",
                    "input-hash",
                    "data/lake/features.parquet",
                    metadata={
                        "efficiency": {
                            "name": "features",
                            "wall_clock_seconds": 2.0,
                            "cpu_seconds": 1.0,
                            "peak_ram_mb": 32.0,
                            "rows_processed": 100,
                            "estimated_cloud_cost_usd": 0.0,
                            "gpu_available": False,
                        }
                    },
                )

                payload = _json_cli(["efficiency", "report", "--run-id", str(run.id)])

                self.assertEqual(payload["run_id"], run.id)
                self.assertEqual(payload["report"]["summary"]["task_count"], 1)
                self.assertEqual(payload["report"]["summary"]["total_rows_processed"], 100)
                self.assertTrue(payload["report"]["quality_gates_passed"])
                self.assertTrue(Path(payload["report_paths"]["json_path"]).exists())
                self.assertTrue(Path(payload["report_paths"]["markdown_path"]).exists())


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _json_cli(argv: list[str]) -> dict[str, object]:
    code, stdout, stderr = _run_cli(argv)
    if code != 0:
        raise AssertionError(f"CLI failed code={code} stderr={stderr}")
    return json.loads(stdout)


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
            "EFFICIENCY_OUTPUT_PATH": str(base_dir / "lake" / "metrics" / "efficiency.jsonl"),
            "EFFICIENCY_REPORT_ROOT": str(base_dir / "reports" / "efficiency"),
        },
        clear=True,
    )


if __name__ == "__main__":
    unittest.main()
