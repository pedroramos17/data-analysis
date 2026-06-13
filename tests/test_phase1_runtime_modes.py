"""Phase 1 runtime modes and RunPod dry-run settings tests."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from src.cli import main as cli_main
from src.config.settings import (
    AUTOSCALING_DEFAULT_MAX_WORKERS,
    AutoscalingSettings,
    CostGuardSettings,
    EfficiencySettings,
    PipelineSettings,
    RateLimitSettings,
    RunPodSettings,
    SecuritySettings,
    SlidingWindowSettings,
    load_runtime_settings,
)
from src.providers.compute.runpod import RunPodComputeProvider
from src.providers.registry import build_provider_registry

ROOT = Path(__file__).resolve().parents[1]


class RuntimeModeSettingsTests(unittest.TestCase):
    def test_local_defaults_are_budget_first(self) -> None:
        settings = load_runtime_settings(env={}, base_dir=ROOT)

        self.assertEqual(settings.app_env, "local")
        self.assertEqual(settings.deployment_mode, "onprem")
        self.assertEqual(settings.database.db_mode, "sqlite")
        self.assertEqual(settings.storage.provider, "local")
        self.assertEqual(settings.duckdb.olap_mode, "duckdb")
        self.assertEqual(settings.compute.provider, "local")
        self.assertEqual(settings.queue.provider, "local")
        self.assertEqual(settings.pipeline.orchestrator, "local")
        self.assertEqual(settings.rate_limit.provider, "memory")
        self.assertEqual(settings.pipeline.model_device, "cpu")
        self.assertEqual(settings.pipeline.cost_mode, "minimum")
        self.assertFalse(settings.compute.gpu_required)
        self.assertFalse(settings.compute.gpu_batch_enabled)
        self.assertFalse(settings.pipeline.external_paid_api_calls_enabled)
        self.assertFalse(settings.pipeline.cloud_tests_enabled)

    def test_new_settings_classes_are_exposed(self) -> None:
        settings = load_runtime_settings(env={}, base_dir=ROOT)

        self.assertIsInstance(settings.pipeline, PipelineSettings)
        self.assertIsInstance(settings.sliding_window, SlidingWindowSettings)
        self.assertIsInstance(settings.runpod, RunPodSettings)
        self.assertIsInstance(settings.autoscaling, AutoscalingSettings)
        self.assertIsInstance(settings.rate_limit, RateLimitSettings)
        self.assertIsInstance(settings.efficiency, EfficiencySettings)
        self.assertIsInstance(settings.cost, CostGuardSettings)
        self.assertIsInstance(settings.security, SecuritySettings)
        self.assertGreaterEqual(AUTOSCALING_DEFAULT_MAX_WORKERS, 1)

    def test_cloud_gpu_defaults_plan_runpod_without_credentials(self) -> None:
        settings = load_runtime_settings(
            env={"APP_ENV": "cloud", "DEPLOYMENT_MODE": "cloud_gpu"},
            base_dir=ROOT,
        )
        registry = build_provider_registry(settings)

        self.assertEqual(settings.database.db_mode, "sqlite")
        self.assertEqual(settings.storage.provider, "local")
        self.assertEqual(settings.compute.provider, "runpod")
        self.assertTrue(settings.runpod.dry_run)
        self.assertIsInstance(registry.get_compute(), RunPodComputeProvider)

        submission = registry.get_compute().submit_job(
            {"name": "train", "task": "train_mamba", "payload": {"model": "fin_mamba"}}
        )

        self.assertEqual(submission.status, "PLANNED")
        self.assertTrue(submission.metadata["dry_run"])
        self.assertFalse(submission.metadata["job_spec"]["launches_paid_infrastructure"])
        self.assertEqual(submission.metadata["job_spec"]["provider"], "runpod")

    def test_cli_gpu_job_dry_run_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "runpod_dry_run.json"
            env = {
                "APP_ENV": "cloud",
                "DEPLOYMENT_MODE": "cloud_gpu",
                "DB_MODE": "sqlite",
                "STORAGE_PROVIDER": "local",
                "QUEUE_PROVIDER": "local",
                "COMPUTE_PROVIDER": "runpod",
                "RUNPOD_DRY_RUN": "true",
            }
            with patch.dict(os.environ, env, clear=True):
                with redirect_stdout(StringIO()):
                    exit_code = cli_main(["gpu-job-dry-run", "--output", str(output_path)])

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "PLANNED")
        self.assertTrue(payload["metadata"]["dry_run"])
        self.assertFalse(payload["metadata"]["job_spec"]["launches_paid_infrastructure"])

    def test_make_acceptance_targets_are_defined_without_cloud_credentials(self) -> None:
        result = subprocess.run(
            ["make", "-n", "smoke-test", "mvp-demo-local", "gpu-job-dry-run"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("APP_ENV=local", result.stdout)
        self.assertIn("COMPUTE_PROVIDER=local", result.stdout)
        self.assertIn("COMPUTE_PROVIDER=runpod", result.stdout)
        self.assertIn("RUNPOD_DRY_RUN=true", result.stdout)
        self.assertIn("gpu-job-dry-run", result.stdout)


if __name__ == "__main__":
    unittest.main()
