"""Phase 10 autoscaling policy tests."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from src.config.settings import load_runtime_settings
from src.orchestration.autoscaling import (
    ActivePod,
    AutoscalingPolicy,
    QueueMetrics,
    QueuedJob,
    RunPodAutoscaler,
    autoscaling_settings_from_config,
)
from src.providers.registry import build_provider_registry


class Phase10AutoscalingTests(unittest.TestCase):
    """Autoscaling must remain bounded and dry-run safe."""

    def test_autoscaling_settings_parse_phase10_env(self) -> None:
        settings = load_runtime_settings(
            env={
                "AUTOSCALING_ENABLED": "true",
                "AUTOSCALING_MIN_WORKERS": "0",
                "AUTOSCALING_MAX_GPU_WORKERS": "3",
                "AUTOSCALING_MAX_CPU_WORKERS": "2",
                "AUTOSCALING_QUEUE_CHECK_INTERVAL_SECONDS": "15",
                "AUTOSCALING_IDLE_TIMEOUT_SECONDS": "120",
                "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "1.25",
                "AUTOSCALING_MAX_DAILY_BUDGET_USD": "6.5",
                "AUTOSCALING_PREFER_SPOT": "true",
                "AUTOSCALING_BATCH_SMALL_JOBS": "false",
            }
        ).autoscaling

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.max_gpu_workers, 3)
        self.assertEqual(settings.max_concurrent_gpu_jobs, 3)
        self.assertEqual(settings.max_cpu_workers, 2)
        self.assertEqual(settings.queue_check_interval_seconds, 15)
        self.assertEqual(settings.idle_timeout_seconds, 120)
        self.assertEqual(settings.max_hourly_budget_usd, 1.25)
        self.assertEqual(settings.max_daily_budget_usd, 6.5)
        self.assertTrue(settings.prefer_spot)
        self.assertFalse(settings.batch_small_jobs)

    def test_autoscaling_settings_parse_nested_config(self) -> None:
        settings = autoscaling_settings_from_config(
            {
                "autoscaling": {
                    "enabled": True,
                    "min_workers": 0,
                    "max_gpu_workers": 1,
                    "max_cpu_workers": 2,
                    "queue_check_interval_seconds": 30,
                    "idle_timeout_seconds": 300,
                    "max_hourly_budget_usd": 1.0,
                    "max_daily_budget_usd": 5.0,
                    "prefer_spot": True,
                    "batch_small_jobs": True,
                }
            }
        )

        self.assertTrue(settings.enabled)
        self.assertEqual(settings.max_gpu_workers, 1)
        self.assertEqual(settings.max_cpu_workers, 2)
        self.assertTrue(settings.batch_small_jobs)

    def test_policy_never_exceeds_max_gpu_workers(self) -> None:
        settings = load_runtime_settings(
            env={
                "AUTOSCALING_ENABLED": "true",
                "AUTOSCALING_MAX_GPU_WORKERS": "1",
                "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "5",
            }
        ).autoscaling
        metrics = QueueMetrics.from_payloads(
            [
                _gpu_job("gpu-1", runtime=1200),
                _gpu_job("gpu-2", runtime=1200),
                _gpu_job("gpu-3", runtime=1200),
            ]
        )

        decision = AutoscalingPolicy(settings, gpu_hourly_cost_usd=0.5).evaluate(metrics)

        self.assertEqual(decision.action, "scale_up")
        self.assertLessEqual(decision.target_gpu_workers, 1)
        self.assertEqual(len(decision.gpu_jobs_to_launch), 1)

    def test_policy_never_exceeds_budget(self) -> None:
        settings = load_runtime_settings(
            env={
                "AUTOSCALING_ENABLED": "true",
                "AUTOSCALING_MAX_GPU_WORKERS": "2",
                "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "0.25",
            }
        ).autoscaling
        metrics = QueueMetrics.from_payloads([_gpu_job("gpu-1", runtime=1200)])

        decision = AutoscalingPolicy(settings, gpu_hourly_cost_usd=0.5).evaluate(metrics)

        self.assertEqual(decision.action, "stay")
        self.assertEqual(decision.target_gpu_workers, 0)
        self.assertEqual(decision.gpu_jobs_to_launch, ())
        self.assertTrue(any("budget" in reason for reason in decision.reasons))

    def test_policy_prefers_cpu_for_small_non_mandatory_jobs(self) -> None:
        settings = load_runtime_settings(
            env={"AUTOSCALING_ENABLED": "true", "AUTOSCALING_MAX_CPU_WORKERS": "2"}
        ).autoscaling
        metrics = QueueMetrics.from_payloads(
            [
                {
                    "job_id": "small-mamba",
                    "model_type": "fin_mamba",
                    "estimated_runtime_seconds": 300,
                    "dataset_size_gb": 0.5,
                    "requires_gpu": False,
                }
            ]
        )

        decision = AutoscalingPolicy(settings).evaluate(metrics)

        self.assertEqual(decision.action, "stay")
        self.assertEqual([job.job_id for job in decision.cpu_jobs_to_run], ["small-mamba"])
        self.assertEqual(decision.gpu_jobs_to_launch, ())

    def test_policy_batches_small_gpu_jobs_when_cost_efficient(self) -> None:
        settings = load_runtime_settings(
            env={
                "AUTOSCALING_ENABLED": "true",
                "AUTOSCALING_MAX_GPU_WORKERS": "2",
                "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "5",
                "AUTOSCALING_BATCH_SMALL_JOBS": "true",
            }
        ).autoscaling
        metrics = QueueMetrics.from_payloads(
            [
                _gpu_job("window-1", runtime=300, dataset_size=0.5, gpu_memory_gb=4),
                _gpu_job("window-2", runtime=300, dataset_size=0.5, gpu_memory_gb=4),
            ]
        )

        decision = AutoscalingPolicy(settings, gpu_hourly_cost_usd=0.5).evaluate(metrics)

        self.assertEqual(decision.action, "scale_up")
        self.assertEqual([job.job_id for job in decision.batched_gpu_jobs], ["window-1", "window-2"])
        self.assertEqual(decision.target_gpu_workers, 1)

    def test_policy_terminates_idle_pods_after_queue_drains(self) -> None:
        settings = load_runtime_settings(
            env={"AUTOSCALING_ENABLED": "true", "AUTOSCALING_IDLE_TIMEOUT_SECONDS": "300"}
        ).autoscaling
        now = datetime.now(UTC)
        metrics = QueueMetrics(
            queued_jobs=(),
            active_pods=(
                ActivePod("pod-1", running_jobs=0, last_active_at=now - timedelta(seconds=600)),
            ),
            observed_at=now,
        )

        decision = AutoscalingPolicy(settings).evaluate(metrics)

        self.assertEqual(decision.action, "scale_down")
        self.assertEqual([pod.pod_id for pod in decision.pods_to_terminate], ["pod-1"])
        self.assertEqual(decision.target_gpu_workers, 0)

    def test_runpod_autoscaler_dry_run_simulates_without_launching(self) -> None:
        settings = load_runtime_settings(
            env={
                "COMPUTE_PROVIDER": "runpod",
                "AUTOSCALING_ENABLED": "true",
                "AUTOSCALING_MAX_GPU_WORKERS": "1",
                "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "5",
            }
        )
        registry = build_provider_registry(settings)
        metrics = QueueMetrics.from_payloads([_gpu_job("gpu-1", runtime=1200)])

        result = RunPodAutoscaler(registry, dry_run=True).tick(metrics)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.decision.action, "scale_up")
        self.assertEqual(result.launched[0]["status"], "SIMULATED")
        self.assertEqual(registry.get_compute().get_status("gpu-1").status, "UNKNOWN")

    def test_failure_rate_blocks_scale_up(self) -> None:
        settings = load_runtime_settings(
            env={"AUTOSCALING_ENABLED": "true", "AUTOSCALING_MAX_HOURLY_BUDGET_USD": "5"}
        ).autoscaling
        metrics = QueueMetrics.from_payloads([_gpu_job("gpu-1", runtime=1200)], failure_rate=0.75)

        decision = AutoscalingPolicy(settings).evaluate(metrics)

        self.assertEqual(decision.action, "stay")
        self.assertTrue(any("failure rate" in reason for reason in decision.reasons))


def _gpu_job(
    job_id: str,
    *,
    runtime: int,
    dataset_size: float = 1.0,
    gpu_memory_gb: int = 16,
) -> QueuedJob:
    return QueuedJob(
        job_id=job_id,
        model_type="fin_mamba",
        estimated_runtime_seconds=runtime,
        dataset_size_gb=dataset_size,
        gpu_memory_gb=gpu_memory_gb,
        requires_gpu=True,
    )


if __name__ == "__main__":
    unittest.main()
