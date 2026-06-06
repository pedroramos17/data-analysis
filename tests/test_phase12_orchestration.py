"""Phase 12 orchestrated pipeline DAG tests."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.orchestration import LocalPipelineRunner, PipelineStateStore, default_pipeline_dag
from src.orchestration.dag import PIPELINE_TASK_ORDER
from src.orchestration.tasks import TaskContext, TaskResult, default_task_handlers
from src.providers.registry import build_provider_registry


class Phase12OrchestrationTests(unittest.TestCase):
    """Pipeline DAG runs should be local-first, resumable, and traceable."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        settings = load_runtime_settings(env={"APP_ENV": "test"}, base_dir=self.tmpdir)
        self.registry = build_provider_registry(settings)
        self.state = PipelineStateStore.from_settings(settings)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_default_dag_matches_required_pipeline_order(self) -> None:
        dag = default_pipeline_dag()

        self.assertEqual(dag.task_names(), PIPELINE_TASK_ORDER)
        self.assertEqual(dag.edges()[0], ("ingest_raw", "preprocess"))
        self.assertEqual(dag.edges()[-1], ("risk_report", "aggregate_report"))

    def test_dry_run_prints_graph_without_persisting(self) -> None:
        runner = LocalPipelineRunner(self.registry, self.state)

        result = runner.dry_run(_pipeline_config(periods=5))

        self.assertEqual(result["status"], "DRY_RUN")
        self.assertEqual(len(result["graph"]["tasks"]), len(PIPELINE_TASK_ORDER))
        with self.assertRaises(ValueError):
            self.state.get_run(1)

    def test_one_command_style_runner_executes_full_local_mvp(self) -> None:
        runner = LocalPipelineRunner(self.registry, self.state)

        result = runner.run(_pipeline_config(periods=8))

        self.assertEqual(result.run.status, "COMPLETED")
        task_names = [task.task_name for task in result.tasks]
        self.assertEqual(task_names, list(PIPELINE_TASK_ORDER))
        self.assertIn("aggregate_report", result.artifacts)
        self.assertTrue(result.artifacts["aggregate_report"])
        status = runner.status(result.run.id)
        self.assertEqual(status["run"]["status"], "COMPLETED")
        self.assertTrue(all(task["input_hash"] for task in status["tasks"]))
        self.assertTrue(all(task["output_uri"] for task in status["tasks"]))

    def test_failed_pipeline_can_resume_and_skip_completed_tasks(self) -> None:
        attempts = {"preprocess": 0}
        handlers = default_task_handlers()
        handlers["ingest_raw"] = _simple_handler("ingested")

        def flaky_preprocess(context: TaskContext) -> TaskResult:
            attempts["preprocess"] += 1
            raise RuntimeError("transient preprocess failure")

        handlers["preprocess"] = flaky_preprocess
        runner = LocalPipelineRunner(self.registry, self.state, handlers)
        config = {
            "name": "resume_test",
            "pipeline": {"name": "resume_test", "tasks": ["ingest_raw", "preprocess"]},
            "retries": {"max_attempts": 1, "backoff_seconds": 0},
        }

        failed = runner.run(config)

        self.assertEqual(failed.run.status, "FAILED")
        ingest_record = self.state.get_task(failed.run.id, "ingest_raw")
        self.assertIsNotNone(ingest_record)
        self.assertEqual(ingest_record.status, "COMPLETED")
        self.assertEqual(self.state.get_task(failed.run.id, "preprocess").status, "FAILED")

        resumed_handlers = default_task_handlers()
        resumed_handlers["ingest_raw"] = _simple_handler("ingested-again")
        resumed_handlers["preprocess"] = _simple_handler("preprocessed")
        resumed = LocalPipelineRunner(self.registry, self.state, resumed_handlers).resume(failed.run.id)

        self.assertEqual(resumed.run.status, "COMPLETED")
        resumed_ingest = self.state.get_task(failed.run.id, "ingest_raw")
        self.assertEqual(resumed_ingest.id, ingest_record.id)
        self.assertEqual(resumed_ingest.output_uri, ingest_record.output_uri)
        self.assertEqual(self.state.get_task(failed.run.id, "preprocess").status, "COMPLETED")


def _pipeline_config(periods: int) -> dict[str, object]:
    return {
        "name": "phase12_test_pipeline",
        "pipeline": {"name": "phase12_test_pipeline", "tasks": list(PIPELINE_TASK_ORDER)},
        "retries": {"max_attempts": 2, "backoff_seconds": 0},
        "mvp_demo": {
            "enabled": True,
            "run_id": "phase12_test_pipeline",
            "symbols": ["SPY"],
            "asset_type": "equity",
            "timeframe": "1d",
            "start": "2024-01-01",
            "periods": periods,
            "source": "sample",
            "feature_version": "phase12_v1",
            "model_name": "naive_return",
            "model_version": "phase12_v1",
            "horizon": "1d",
            "optional_sequence_models": [],
            "persist_feature_metadata": True,
        },
    }


def _simple_handler(label: str):
    def handler(context: TaskContext) -> TaskResult:
        output = context.lake_root / "pipeline_runs" / context.run_name / f"{context.task_name}.txt"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(label, encoding="utf-8")
        return TaskResult("COMPLETED", output.as_posix(), {context.task_name: output.as_posix()}, {"label": label})

    return handler


if __name__ == "__main__":
    unittest.main()
