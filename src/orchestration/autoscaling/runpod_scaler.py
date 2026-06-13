"""RunPod autoscaler wrapper around the pure autoscaling policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.cli_commands import src_cli_command
from src.config.settings import RuntimeSettings
from src.orchestration.autoscaling.policy import AutoscalingDecision, AutoscalingPolicy
from src.orchestration.autoscaling.queue_metrics import QueueMetrics, QueuedJob
from src.providers.registry import ProviderRegistry


@dataclass(frozen=True, slots=True)
class RunPodScalerResult:
    """Result from one autoscaler tick."""

    decision: AutoscalingDecision
    launched: tuple[dict[str, object], ...] = ()
    terminated: tuple[dict[str, object], ...] = ()
    errors: tuple[str, ...] = ()
    dry_run: bool = True
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly scaler result."""
        return {
            "decision": self.decision.to_dict(),
            "launched": [dict(item) for item in self.launched],
            "terminated": [dict(item) for item in self.terminated],
            "errors": list(self.errors),
            "dry_run": self.dry_run,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class RunPodAutoscaler:
    """Scale RunPod GPU pods from queue metrics through provider facades."""

    registry: ProviderRegistry
    dry_run: bool = True

    @property
    def settings(self) -> RuntimeSettings:
        """Return runtime settings used by this scaler."""
        return self.registry.settings

    def tick(self, metrics: QueueMetrics) -> RunPodScalerResult:
        """Run one autoscaling evaluation and optionally apply it."""
        policy = AutoscalingPolicy(
            self.settings.autoscaling,
            gpu_hourly_cost_usd=self.settings.runpod.max_hourly_cost_usd,
            dry_run=self.dry_run,
        )
        decision = policy.evaluate(metrics)
        if self.dry_run:
            return self._simulate(decision)
        return self._apply(decision)

    def _simulate(self, decision: AutoscalingDecision) -> RunPodScalerResult:
        launched = tuple(
            {
                "job_id": job.job_id,
                "status": "SIMULATED",
                "action": "launch_gpu_pod",
                "batched_job_ids": [item.job_id for item in decision.batched_gpu_jobs],
            }
            for job in self._launch_jobs(decision)
        )
        terminated = tuple(
            {"pod_id": pod.pod_id, "status": "SIMULATED", "action": "terminate_idle_pod"}
            for pod in decision.pods_to_terminate
        )
        return RunPodScalerResult(
            decision=decision,
            launched=launched,
            terminated=terminated,
            dry_run=True,
            metadata={"mode": "simulation"},
        )

    def _apply(self, decision: AutoscalingDecision) -> RunPodScalerResult:
        compute = self.registry.get_compute()
        launched: list[dict[str, object]] = []
        terminated: list[dict[str, object]] = []
        errors: list[str] = []
        for job in self._launch_jobs(decision):
            try:
                submission = compute.submit_job(self._job_spec(job, decision))
            except Exception as exc:
                errors.append(str(exc))
            else:
                launched.append(
                    {
                        "job_id": submission.job_id,
                        "status": submission.status,
                        "metadata": submission.metadata,
                    }
                )
        for pod in decision.pods_to_terminate:
            try:
                submission = compute.cancel_job(pod.pod_id)
            except Exception as exc:
                errors.append(str(exc))
            else:
                terminated.append(
                    {
                        "pod_id": pod.pod_id,
                        "status": submission.status,
                        "metadata": submission.metadata,
                    }
                )
        return RunPodScalerResult(
            decision=decision,
            launched=tuple(launched),
            terminated=tuple(terminated),
            errors=tuple(errors),
            dry_run=False,
            metadata={"mode": "apply"},
        )

    def _launch_jobs(self, decision: AutoscalingDecision) -> tuple[QueuedJob, ...]:
        if decision.batched_gpu_jobs:
            return decision.batched_gpu_jobs[:1]
        return decision.gpu_jobs_to_launch

    def _job_spec(self, job: QueuedJob, decision: AutoscalingDecision) -> dict[str, object]:
        payload = dict(job.payload)
        if decision.batched_gpu_jobs:
            payload["batch_job_ids"] = [item.job_id for item in decision.batched_gpu_jobs]
            payload["window_count"] = sum(max(item.window_count, 1) for item in decision.batched_gpu_jobs)
        payload.setdefault("model_name", job.model_type)
        payload.setdefault("dataset_size_gb", job.dataset_size_gb)
        payload.setdefault(
            "min_gpu_memory_gb",
            job.gpu_memory_gb or self.settings.runpod.min_gpu_memory_gb,
        )
        payload.setdefault(
            "max_runtime_seconds",
            max(job.estimated_runtime_seconds, self.settings.runpod.idle_timeout_seconds),
        )
        payload.setdefault("idle_timeout_seconds", self.settings.runpod.idle_timeout_seconds)
        payload.setdefault("hourly_cost_usd", self.settings.runpod.max_hourly_cost_usd)
        payload.setdefault("confirm_cost", False)
        payload.setdefault("dry_run", self.settings.runpod.dry_run)
        return {
            "name": f"autoscale-{job.job_id}",
            "task": job.task_type,
            "command": str(
                payload.get("command")
                or src_cli_command(
                    "train",
                    "run-windowed",
                    "--config",
                    "configs/train_gpu.yaml",
                )
            ),
            "payload": payload,
            "max_runtime_seconds": payload["max_runtime_seconds"],
            "idle_timeout_seconds": payload["idle_timeout_seconds"],
            "dataset_size_gb": payload["dataset_size_gb"],
            "hourly_cost_usd": payload["hourly_cost_usd"],
            "min_gpu_memory_gb": payload["min_gpu_memory_gb"],
            "dry_run": payload["dry_run"],
            "confirm_cost": payload["confirm_cost"],
        }


def queue_metrics_from_config(payload: Mapping[str, object]) -> QueueMetrics:
    """Build queue metrics from a simple config mapping for simulations."""
    queued_jobs = payload.get("queued_jobs", [])
    active_pods = payload.get("active_pods", [])
    return QueueMetrics.from_payloads(
        queued_jobs if isinstance(queued_jobs, list) else [],
        active_pods if isinstance(active_pods, list) else [],
        budget_spent_today_usd=_float(payload.get("budget_spent_today_usd"), 0.0),
        current_hourly_spend_usd=_float(payload.get("current_hourly_spend_usd"), 0.0),
        failure_rate=_float(payload.get("failure_rate"), 0.0),
    )


def _float(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)
