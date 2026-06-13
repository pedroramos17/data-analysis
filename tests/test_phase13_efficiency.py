"""Phase 13 efficiency profiling and quality gate tests."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.observability.efficiency import (
    build_efficiency_report,
    profile_duckdb_query,
    profile_task,
    profile_training_loop,
    write_efficiency_report,
)
from src.orchestration import LocalPipelineRunner, PipelineStateStore
from src.orchestration.dag import PIPELINE_TASK_ORDER
from src.providers.registry import build_provider_registry


class Phase13EfficiencyTests(unittest.TestCase):
    """Efficiency profiler should be lightweight and CI-safe."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_profile_task_context_records_metrics(self) -> None:
        with profile_task("feature_extraction") as profiler:
            rows = [{"x": value} for value in range(10)]
            profiler.rows_processed = len(rows)
            profiler.parquet_rows = len(rows)

        metric = profiler.metric.to_dict()

        self.assertEqual(metric["name"], "feature_extraction")
        self.assertEqual(metric["category"], "task")
        self.assertEqual(metric["status"], "COMPLETED")
        self.assertGreaterEqual(metric["wall_clock_seconds"], 0.0)
        self.assertGreaterEqual(metric["peak_ram_mb"], 0.0)
        self.assertEqual(metric["rows_processed"], 10)

    def test_decorator_and_specialized_contexts(self) -> None:
        profiler = profile_task("decorated_task")

        @profiler
        def run_task() -> dict[str, int]:
            return {"rows": 5}

        result = run_task()
        with profile_duckdb_query("build_training_panel") as duckdb_profiler:
            duckdb_profiler.duckdb_query_seconds = 0.001
        with profile_training_loop("fin_mamba_train") as training_profiler:
            training_profiler.training_samples = 20
            training_profiler.training_windows = 2

        self.assertEqual(result["rows"], 5)
        self.assertEqual(profiler.metric.to_dict()["rows_processed"], 5)
        self.assertEqual(duckdb_profiler.metric.to_dict()["category"], "duckdb_query")
        self.assertEqual(training_profiler.metric.to_dict()["training_samples"], 20)

    def test_report_shows_slowest_tasks_and_recommendations(self) -> None:
        metrics = [
            {
                "name": "fast",
                "category": "task",
                "status": "COMPLETED",
                "wall_clock_seconds": 1.0,
                "cpu_seconds": 0.5,
                "peak_ram_mb": 128.0,
                "disk_read_mb": 0.0,
                "disk_write_mb": 0.0,
                "rows_processed": 100_000,
                "estimated_cloud_cost_usd": 0.0,
            },
            {
                "name": "slow",
                "category": "task",
                "status": "COMPLETED",
                "wall_clock_seconds": 5.0,
                "cpu_seconds": 4.0,
                "peak_ram_mb": 512.0,
                "disk_read_mb": 0.0,
                "disk_write_mb": 0.0,
                "rows_processed": 50_000,
                "estimated_cloud_cost_usd": 0.0,
            },
        ]

        report = build_efficiency_report(
            7,
            metrics,
            {"efficiency_gates": {"min_rows_per_second": 1000, "max_cost_per_run_usd": 2.0}},
        )
        paths = write_efficiency_report(7, report, self.tmpdir / "reports" / "efficiency")

        self.assertEqual(report["slowest_tasks"][0]["name"], "slow")
        self.assertTrue(report["recommendations"])
        self.assertTrue(Path(paths["json_path"]).exists())
        self.assertTrue(Path(paths["markdown_path"]).exists())

    def test_quality_gates_fail_when_limits_are_exceeded(self) -> None:
        report = build_efficiency_report(
            8,
            [
                {
                    "name": "too_slow",
                    "category": "task",
                    "status": "COMPLETED",
                    "wall_clock_seconds": 120.0,
                    "cpu_seconds": 1.0,
                    "peak_ram_mb": 8192.0,
                    "disk_read_mb": 0.0,
                    "disk_write_mb": 0.0,
                    "rows_processed": 1,
                    "estimated_cloud_cost_usd": 3.0,
                }
            ],
            {
                "efficiency_gates": {
                    "max_pipeline_minutes_local": 1,
                    "max_peak_memory_mb": 4096,
                    "min_rows_per_second": 10000,
                    "max_cost_per_run_usd": 2.0,
                }
            },
        )

        self.assertFalse(report["quality_gates_passed"])
        self.assertFalse(report["quality_gates"]["max_pipeline_minutes_local"]["passed"])
        self.assertFalse(report["quality_gates"]["max_peak_memory_mb"]["passed"])
        self.assertFalse(report["quality_gates"]["max_cost_per_run_usd"]["passed"])

    def test_pipeline_records_efficiency_metrics_and_reports(self) -> None:
        settings = load_runtime_settings(env={"APP_ENV": "test"}, base_dir=self.tmpdir)
        registry = build_provider_registry(settings)
        state = PipelineStateStore.from_settings(settings)
        runner = LocalPipelineRunner(registry, state)

        result = runner.run(_pipeline_config())

        self.assertEqual(result.run.status, "COMPLETED")
        for task in result.tasks:
            self.assertIn("efficiency", task.metadata_json)
            self.assertEqual(task.metadata_json["efficiency"]["name"], task.task_name)
        report_paths = result.run.efficiency_json["report_paths"]
        self.assertTrue(Path(report_paths["json_path"]).exists())
        self.assertTrue(Path(report_paths["markdown_path"]).exists())
        report = result.run.efficiency_json["report"]
        self.assertEqual(report["summary"]["task_count"], len(PIPELINE_TASK_ORDER))
        self.assertTrue(report["slowest_tasks"])
        self.assertTrue(report["recommendations"])


def _pipeline_config() -> dict[str, object]:
    return {
        "name": "phase13_efficiency_smoke",
        "pipeline": {"name": "phase13_efficiency_smoke", "tasks": list(PIPELINE_TASK_ORDER)},
        "retries": {"max_attempts": 1, "backoff_seconds": 0},
        "efficiency_gates": {
            "max_pipeline_minutes_local": 30,
            "max_peak_memory_mb": 4096,
            "min_rows_per_second": 10000,
            "max_gpu_job_minutes": 60,
            "max_cost_per_run_usd": 2.0,
        },
        "mvp_demo": {
            "enabled": True,
            "run_id": "phase13_efficiency_smoke",
            "symbols": ["SPY"],
            "asset_type": "equity",
            "timeframe": "1d",
            "start": "2024-01-01",
            "periods": 5,
            "source": "sample",
            "feature_version": "phase13_v1",
            "model_name": "naive_return",
            "model_version": "phase13_v1",
            "horizon": "1d",
            "optional_sequence_models": [],
            "persist_feature_metadata": True,
        },
    }


if __name__ == "__main__":
    unittest.main()
