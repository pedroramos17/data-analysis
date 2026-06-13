"""Phase 14 cost minimization strategy tests."""

from __future__ import annotations

import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.cli import main as cli_main
from src.config.settings import load_runtime_settings
from src.cost import BudgetGuard, estimate_costs, plan_costs


class Phase14CostPlanningTests(unittest.TestCase):
    """Cost planning must prefer local and block unsafe GPU spend."""

    def test_baseline_models_never_choose_gpu_by_default(self) -> None:
        settings = load_runtime_settings(env={"RUNPOD_DRY_RUN": "false"})
        plan = plan_costs(
            {
                "model_name": "naive_return",
                "dataset_size_gb": 25,
                "estimated_runtime_seconds": 1800,
                "hourly_cost_usd": 0.5,
            },
            settings,
        )

        self.assertEqual(plan.selected_option.name, "local_cpu")
        self.assertFalse(plan.selected_option.launches_paid_infrastructure)
        self.assertFalse(any(step.action.startswith("submit_runpod") for step in plan.steps))

    def test_small_sequence_dataset_stays_local_unless_gpu_is_forced(self) -> None:
        settings = load_runtime_settings(env={})
        plan = plan_costs(
            {
                "model_name": "fin_mamba",
                "dataset_size_gb": 0.5,
                "estimated_runtime_seconds": 600,
                "device": "auto",
            },
            settings,
        )

        self.assertEqual(plan.selected_option.name, "local_cpu")
        self.assertFalse(plan.selected_option.launches_paid_infrastructure)

    def test_budget_guard_blocks_expensive_gpu_config(self) -> None:
        settings = load_runtime_settings(
            env={
                "RUNPOD_DRY_RUN": "false",
                "CLOUD_MAX_JOB_COST_USD": "0.20",
                "EFFICIENCY_MAX_COST_PER_RUN_USD": "5.0",
                "RUNPOD_MAX_HOURLY_COST": "2.0",
                "MAX_GPU_HOURLY_COST_USD": "2.0",
                "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "5.0",
                "AUTOSCALING_MAX_DAILY_BUDGET_USD": "5.0",
            }
        )
        option = estimate_costs(
            {
                "model_name": "fin_mamba",
                "force_gpu": True,
                "dataset_size_gb": 8,
                "max_runtime_seconds": 3500,
                "hourly_cost_usd": 1.0,
            },
            settings,
        ).option("runpod_gpu")

        result = BudgetGuard(settings).check_option(option, confirm_cost=True)

        self.assertFalse(result.allowed)
        self.assertIn("estimated job cost exceeds CLOUD_MAX_JOB_COST_USD", result.violations)

    def test_smoke_mode_downsamples_and_selects_one_window(self) -> None:
        plan = plan_costs(
            {
                "model_name": "fin_mamba",
                "smoke_mode": True,
                "dataset_size_gb": 10,
                "window_count": 12,
                "estimated_runtime_seconds": 2400,
            },
            load_runtime_settings(env={}),
        )

        self.assertEqual(plan.selected_option.name, "local_smoke")
        self.assertEqual(plan.selected_option.window_count, 1)
        self.assertEqual(plan.selected_option.metadata["sample_fraction"], 0.1)
        self.assertTrue(any(step.action == "downsample_smoke" or "smoke" in step.action for step in plan.steps))

    def test_batching_windows_is_chosen_when_cheaper(self) -> None:
        settings = load_runtime_settings(
            env={
                "RUNPOD_DRY_RUN": "false",
                "CLOUD_MAX_JOB_COST_USD": "5.0",
                "EFFICIENCY_MAX_COST_PER_RUN_USD": "5.0",
                "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "5.0",
                "AUTOSCALING_MAX_DAILY_BUDGET_USD": "5.0",
            }
        )
        plan = plan_costs(
            {
                "model_name": "fin_mamba",
                "force_gpu": True,
                "full_training": True,
                "dataset_size_gb": 5,
                "window_count": 3,
                "estimated_runtime_seconds": 900,
                "max_runtime_seconds": 1200,
                "hourly_cost_usd": 0.5,
            },
            settings,
            confirm_cost=True,
        )

        runpod = plan.estimate.option("runpod_gpu")
        batched = plan.estimate.option("runpod_batched_gpu")
        self.assertLess(batched.estimated_cost_usd, runpod.estimated_cost_usd)
        self.assertEqual(plan.selected_option.name, "runpod_batched_gpu")

    def test_cached_features_and_pretrained_model_reduce_runtime(self) -> None:
        settings = load_runtime_settings(env={})
        base = estimate_costs(
            {
                "model_name": "fin_mamba",
                "force_gpu": True,
                "dataset_size_gb": 5,
                "max_runtime_seconds": 1000,
                "hourly_cost_usd": 0.5,
            },
            settings,
        ).option("runpod_gpu")
        cached = estimate_costs(
            {
                "model_name": "fin_mamba",
                "force_gpu": True,
                "dataset_size_gb": 5,
                "max_runtime_seconds": 1000,
                "hourly_cost_usd": 0.5,
                "reuse_cached_features": True,
                "pretrained_model_uri": "models://fin_mamba/base",
            },
            settings,
        ).option("runpod_gpu")

        self.assertLess(cached.estimated_runtime_seconds, base.estimated_runtime_seconds)
        self.assertIn("cached_features", cached.metadata["runtime_reduction_reasons"])
        self.assertIn("pretrained_model", cached.metadata["runtime_reduction_reasons"])

    def test_spot_capacity_is_preferred_when_enabled(self) -> None:
        settings = load_runtime_settings(
            env={
                "RUNPOD_ENABLE_SPOT": "true",
                "AUTOSCALING_PREFER_SPOT": "true",
            }
        )
        plan = plan_costs(
            {
                "model_name": "fin_mamba",
                "force_gpu": True,
                "full_training": True,
                "dataset_size_gb": 4,
                "max_runtime_seconds": 600,
                "hourly_cost_usd": 0.5,
            },
            settings,
        )

        self.assertEqual(plan.selected_option.provider, "runpod")
        self.assertTrue(plan.selected_option.metadata["prefer_spot"])
        self.assertTrue(any(step.action == "prefer_spot_capacity" for step in plan.steps))

    def test_cost_cli_prints_plan_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "train.json"
            config_path.write_text(json.dumps({"model_name": "naive_return"}), encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout):
                exit_code = cli_main(["cost", "plan", "--config", str(config_path)])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["selected_option"]["name"], "local_cpu")

    def test_paid_runpod_submit_prints_preflight_before_refusing_local_plan(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "baseline.json"
            config_path.write_text(json.dumps(_remote_baseline_config()), encoding="utf-8")
            stdout = StringIO()
            stderr = StringIO()
            env = {
                "RUNPOD_DRY_RUN": "false",
                "RUNPOD_API_KEY": "secret-token",
                "CLOUD_MAX_JOB_COST_USD": "5.0",
                "EFFICIENCY_MAX_COST_PER_RUN_USD": "5.0",
                "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "5.0",
                "AUTOSCALING_MAX_DAILY_BUDGET_USD": "5.0",
            }

            with patch.dict(os.environ, env, clear=True), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli_main(
                    ["compute", "runpod", "submit", "--config", str(config_path), "--confirm-cost"]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("cost_preflight", stderr.getvalue())
        self.assertIn("refusing paid RunPod submit", stderr.getvalue())


def _remote_baseline_config() -> dict[str, object]:
    return {
        "model_name": "naive_return",
        "dataset_uri": "s3://bucket/datasets/baseline",
        "output_uri": "s3://bucket/models/baseline",
        "logs_uri": "s3://bucket/logs/baseline",
        "metrics_uri": "s3://bucket/metrics/baseline",
        "config_path": "configs/train.yaml",
        "max_runtime_seconds": 600,
        "idle_timeout_seconds": 300,
        "hourly_cost_usd": 0.5,
    }


if __name__ == "__main__":
    unittest.main()
