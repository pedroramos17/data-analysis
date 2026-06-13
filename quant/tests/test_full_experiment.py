"""Quant safe full-experiment orchestrator tests."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase


class QuantFullExperimentCommandTests(TestCase):
    """The full experiment command should orchestrate safely by default."""

    def test_dry_run_prints_dag(self) -> None:
        """Dry-run prints the fixed research DAG and stores a DRY_RUN experiment."""
        from quant.models import Experiment

        stdout = StringIO()

        call_command(
            "quant_run_full_experiment",
            "--name",
            "global_macro_quant_v1",
            "--symbols",
            "SPY,QQQ",
            "--asset-classes",
            "stocks,indices",
            "--timeframes",
            "1d,1h",
            "--dry-run",
            "--no-live-trading",
            stdout=stdout,
        )

        output = stdout.getvalue()
        experiment = Experiment.objects.get(name="global_macro_quant_v1")
        self.assertIn("Data -> Windows -> Features", output)
        self.assertIn("Portfolio -> Backtest -> Explainability", output)
        self.assertEqual(experiment.status, "DRY_RUN")

    def test_experiment_status_updates_correctly_when_data_missing(self) -> None:
        """Missing data produces skipped steps and a completed-with-skips status."""
        from quant.models import Experiment

        stdout = StringIO()

        call_command(
            "quant_run_full_experiment",
            "--name",
            "missing-data-run",
            "--symbols",
            "SPY",
            "--timeframes",
            "1d",
            "--execute",
            "--no-live-trading",
            stdout=stdout,
        )

        experiment = Experiment.objects.get(name="missing-data-run")
        steps = experiment.provenance_json["orchestrator"]["steps"]
        self.assertEqual(experiment.status, "COMPLETED_WITH_SKIPS")
        self.assertEqual(steps[0]["status"], "SKIPPED")
        self.assertIn("missing local data", steps[0]["reason"])

    def test_completed_step_records_artifact_paths(self) -> None:
        """A completed data step stores local artifact paths without fake metrics."""
        from quant.models import Experiment

        with TemporaryDirectory() as data_root:
            Path(data_root, "SPY_1d.csv").write_text("date,close\n", encoding="utf-8")
            call_command(
                "quant_run_full_experiment",
                "--name",
                "artifact-run",
                "--symbols",
                "SPY",
                "--timeframes",
                "1d",
                "--data-root",
                data_root,
                "--execute",
                "--no-live-trading",
                stdout=StringIO(),
            )

        experiment = Experiment.objects.get(name="artifact-run")
        data_step = experiment.provenance_json["orchestrator"]["steps"][0]
        self.assertEqual(data_step["status"], "COMPLETED")
        self.assertTrue(data_step["artifact_paths"][0].endswith("SPY_1d.csv"))
        self.assertNotIn("metrics", data_step)


class QuantFullExperimentServiceTests(TestCase):
    """The orchestration service should record safe step outcomes."""

    def test_missing_optional_deps_skipped_clearly(self) -> None:
        """Optional components are skipped when dependencies are unavailable."""
        from quant.services.full_experiment import (
            FullExperimentConfig,
            run_full_experiment,
        )

        config = FullExperimentConfig(
            name="optional-skip-run",
            models=["tcn"],
            graphs=["pmfg"],
            dry_run=False,
        )
        result = run_full_experiment(config, dependency_checker=lambda module: False)
        output = "\n".join(result.output_lines)

        self.assertEqual(result.experiment.status, "COMPLETED_WITH_SKIPS")
        self.assertIn("torch", output)
        self.assertIn("optional dependency", output)

    def test_no_live_trading_is_enforced(self) -> None:
        """The orchestrator rejects any config that enables live trading."""
        from quant.services.full_experiment import (
            FullExperimentConfig,
            run_full_experiment,
        )

        config = FullExperimentConfig(name="unsafe-run", live_trading=True)

        with self.assertRaisesRegex(ValueError, "live_trading"):
            run_full_experiment(config)

    def test_failed_step_records_error_metadata(self) -> None:
        """A failed runner marks the experiment failed and records the error."""
        from quant.models import Experiment
        from quant.services.full_experiment import (
            FullExperimentConfig,
            StepExecutionResult,
            run_full_experiment,
        )

        def fail_data_step(config: object) -> StepExecutionResult:
            raise RuntimeError("fixture failure")

        config = FullExperimentConfig(name="failed-run", dry_run=False)
        run_full_experiment(config, step_runners={"Data": fail_data_step})

        experiment = Experiment.objects.get(name="failed-run")
        data_step = experiment.provenance_json["orchestrator"]["steps"][0]
        self.assertEqual(experiment.status, "FAILED")
        self.assertEqual(data_step["status"], "FAILED")
        self.assertIn("fixture failure", data_step["error"]["message"])
