"""Pure autoscaling policy for training and inference queues."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.config.settings import AutoscalingSettings
from src.orchestration.autoscaling.cost_guard import AutoscalingBudget, AutoscalingCostGuard
from src.orchestration.autoscaling.queue_metrics import ActivePod, QueueMetrics, QueuedJob

FAILURE_RATE_STOP_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class AutoscalingDecision:
    """Result of one autoscaling policy evaluation."""

    action: str
    target_gpu_workers: int
    target_cpu_workers: int
    gpu_jobs_to_launch: tuple[QueuedJob, ...] = ()
    cpu_jobs_to_run: tuple[QueuedJob, ...] = ()
    batched_gpu_jobs: tuple[QueuedJob, ...] = ()
    pods_to_terminate: tuple[ActivePod, ...] = ()
    dry_run: bool = True
    reasons: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly decision payload."""
        return {
            "action": self.action,
            "target_gpu_workers": self.target_gpu_workers,
            "target_cpu_workers": self.target_cpu_workers,
            "gpu_jobs_to_launch": [job.job_id for job in self.gpu_jobs_to_launch],
            "cpu_jobs_to_run": [job.job_id for job in self.cpu_jobs_to_run],
            "batched_gpu_jobs": [job.job_id for job in self.batched_gpu_jobs],
            "pods_to_terminate": [pod.pod_id for pod in self.pods_to_terminate],
            "dry_run": self.dry_run,
            "reasons": list(self.reasons),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AutoscalingPolicy:
    """Compute scale-up/down actions from queue and budget signals."""

    settings: AutoscalingSettings
    gpu_hourly_cost_usd: float = 0.75
    dry_run: bool = True

    def evaluate(self, metrics: QueueMetrics) -> AutoscalingDecision:
        """Evaluate one autoscaling tick."""
        if not self.settings.enabled:
            return AutoscalingDecision(
                action="disabled",
                target_gpu_workers=0,
                target_cpu_workers=0,
                dry_run=self.dry_run,
                reasons=("autoscaling disabled",),
            )

        active_gpu_pods = metrics.active_gpu_pods
        idle_pods = self._idle_pods(metrics)
        cpu_jobs, gpu_candidates = self._partition_jobs(metrics.queued_jobs)
        max_gpu_workers = self._max_gpu_workers()
        target_cpu_workers = min(len(cpu_jobs), self.settings.max_cpu_workers)
        reasons: list[str] = [
            f"queue_length={metrics.queue_length}",
            f"active_gpu_pods={len(active_gpu_pods)}",
            f"failure_rate={max(metrics.failure_rate, self._job_failure_rate(metrics.queued_jobs)):.3f}",
        ]

        if metrics.queue_length == 0:
            reasons.append("queue drained")
            return AutoscalingDecision(
                action="scale_down" if idle_pods else "stay",
                target_gpu_workers=max(self.settings.min_workers, len(active_gpu_pods) - len(idle_pods)),
                target_cpu_workers=0,
                pods_to_terminate=idle_pods,
                dry_run=self.dry_run,
                reasons=tuple(reasons),
                metadata=self._metadata(metrics, max_gpu_workers),
            )

        failure_rate = max(metrics.failure_rate, self._job_failure_rate(metrics.queued_jobs))
        if failure_rate >= FAILURE_RATE_STOP_THRESHOLD:
            reasons.append("failure rate too high for scale-up")
            return AutoscalingDecision(
                action="stay",
                target_gpu_workers=min(len(active_gpu_pods), max_gpu_workers),
                target_cpu_workers=target_cpu_workers,
                cpu_jobs_to_run=tuple(cpu_jobs[: self.settings.max_cpu_workers]),
                dry_run=self.dry_run,
                reasons=tuple(reasons),
                metadata=self._metadata(metrics, max_gpu_workers),
            )

        if not gpu_candidates:
            reasons.append("no queued GPU jobs")
            return AutoscalingDecision(
                action="scale_down" if idle_pods else "stay",
                target_gpu_workers=max(self.settings.min_workers, len(active_gpu_pods) - len(idle_pods)),
                target_cpu_workers=target_cpu_workers,
                cpu_jobs_to_run=tuple(cpu_jobs[: self.settings.max_cpu_workers]),
                pods_to_terminate=idle_pods,
                dry_run=self.dry_run,
                reasons=tuple(reasons),
                metadata=self._metadata(metrics, max_gpu_workers),
            )

        available_slots = max(max_gpu_workers - len(active_gpu_pods), 0)
        if available_slots <= 0:
            reasons.append("max GPU workers reached")
            return AutoscalingDecision(
                action="stay",
                target_gpu_workers=min(len(active_gpu_pods), max_gpu_workers),
                target_cpu_workers=target_cpu_workers,
                cpu_jobs_to_run=tuple(cpu_jobs[: self.settings.max_cpu_workers]),
                dry_run=self.dry_run,
                reasons=tuple(reasons),
                metadata=self._metadata(metrics, max_gpu_workers),
            )

        batched_jobs = self._batched_jobs(gpu_candidates)
        launch_jobs = batched_jobs[:1] if batched_jobs else tuple(gpu_candidates[:available_slots])
        budget_allowed, budget_reason = self._budget_allows(metrics, len(launch_jobs), gpu_candidates)
        reasons.append(budget_reason)
        if not budget_allowed:
            return AutoscalingDecision(
                action="stay",
                target_gpu_workers=len(active_gpu_pods),
                target_cpu_workers=target_cpu_workers,
                cpu_jobs_to_run=tuple(cpu_jobs[: self.settings.max_cpu_workers]),
                dry_run=self.dry_run,
                reasons=tuple(reasons),
                metadata=self._metadata(metrics, max_gpu_workers),
            )

        target_gpu_workers = min(len(active_gpu_pods) + len(launch_jobs), max_gpu_workers)
        action = "scale_up" if launch_jobs else "stay"
        return AutoscalingDecision(
            action=action,
            target_gpu_workers=target_gpu_workers,
            target_cpu_workers=target_cpu_workers,
            gpu_jobs_to_launch=tuple(launch_jobs),
            cpu_jobs_to_run=tuple(cpu_jobs[: self.settings.max_cpu_workers]),
            batched_gpu_jobs=tuple(batched_jobs),
            pods_to_terminate=idle_pods,
            dry_run=self.dry_run,
            reasons=tuple(reasons),
            metadata=self._metadata(metrics, max_gpu_workers),
        )

    def _partition_jobs(self, jobs: tuple[QueuedJob, ...]) -> tuple[list[QueuedJob], list[QueuedJob]]:
        cpu_jobs: list[QueuedJob] = []
        gpu_jobs: list[QueuedJob] = []
        for job in jobs:
            if self._prefer_cpu(job):
                cpu_jobs.append(job)
            elif job.prefers_gpu():
                gpu_jobs.append(job)
            else:
                cpu_jobs.append(job)
        return cpu_jobs, gpu_jobs

    def _prefer_cpu(self, job: QueuedJob) -> bool:
        return job.is_small() and not job.requires_gpu and job.gpu_memory_gb == 0

    def _batched_jobs(self, gpu_jobs: list[QueuedJob]) -> tuple[QueuedJob, ...]:
        if not self.settings.batch_small_jobs:
            return ()
        small_jobs = tuple(job for job in gpu_jobs if job.is_small())
        if len(small_jobs) < 2:
            return ()
        separate_cost = sum(max(job.estimated_runtime_seconds, 60) for job in small_jobs) * self.gpu_hourly_cost_usd / 3600.0
        batched_runtime = max(job.estimated_runtime_seconds for job in small_jobs) + 60
        batched_cost = batched_runtime * self.gpu_hourly_cost_usd / 3600.0
        if batched_cost < separate_cost:
            return small_jobs
        return ()

    def _budget_allows(
        self,
        metrics: QueueMetrics,
        launch_count: int,
        gpu_jobs: list[QueuedJob],
    ) -> tuple[bool, str]:
        if launch_count <= 0:
            return True, "no GPU launch needed"
        runtime_seconds = max((job.estimated_runtime_seconds for job in gpu_jobs), default=0)
        budget = AutoscalingBudget(
            current_hourly_spend_usd=metrics.current_hourly_spend_usd,
            spent_today_usd=metrics.budget_spent_today_usd,
            candidate_hourly_cost_usd=self.gpu_hourly_cost_usd * launch_count,
            candidate_runtime_seconds=runtime_seconds,
        )
        return AutoscalingCostGuard(self.settings).can_launch(budget)

    def _idle_pods(self, metrics: QueueMetrics) -> tuple[ActivePod, ...]:
        return tuple(
            pod for pod in metrics.active_gpu_pods if pod.is_idle(metrics.observed_at, self.settings.idle_timeout_seconds)
        )

    def _max_gpu_workers(self) -> int:
        return max(
            min(
                self.settings.max_gpu_workers,
                self.settings.max_concurrent_gpu_jobs,
                self.settings.max_workers,
            ),
            0,
        )

    def _metadata(self, metrics: QueueMetrics, max_gpu_workers: int) -> dict[str, object]:
        guard = AutoscalingCostGuard(self.settings)
        return {
            "max_gpu_workers": max_gpu_workers,
            "max_cpu_workers": self.settings.max_cpu_workers,
            "queue_check_interval_seconds": self.settings.queue_check_interval_seconds,
            "budget_remaining_hourly_usd": guard.remaining_hourly_budget_usd(metrics.current_hourly_spend_usd),
            "budget_remaining_daily_usd": guard.remaining_daily_budget_usd(metrics.budget_spent_today_usd),
            "prefer_spot": self.settings.prefer_spot,
            "batch_small_jobs": self.settings.batch_small_jobs,
            "max_gpu_memory_needed_gb": metrics.max_gpu_memory_needed_gb(),
            "max_dataset_size_gb": metrics.max_dataset_size_gb(),
        }

    def _job_failure_rate(self, jobs: tuple[QueuedJob, ...]) -> float:
        return max((job.failure_rate for job in jobs), default=0.0)


def autoscaling_settings_from_config(config: Mapping[str, object]) -> AutoscalingSettings:
    """Build autoscaling settings from an `autoscaling:` config block."""
    payload = config.get("autoscaling", config)
    if not isinstance(payload, Mapping):
        payload = {}
    max_gpu_workers = _int(payload.get("max_gpu_workers"), 1)
    return AutoscalingSettings(
        enabled=_bool(payload.get("enabled"), False),
        min_workers=_int(payload.get("min_workers"), 0),
        max_workers=max(max_gpu_workers, _int(payload.get("max_workers"), max_gpu_workers)),
        max_concurrent_gpu_jobs=max_gpu_workers,
        max_gpu_workers=max_gpu_workers,
        max_cpu_workers=_int(payload.get("max_cpu_workers"), 2),
        queue_check_interval_seconds=_int(payload.get("queue_check_interval_seconds"), 30),
        scale_to_zero=_bool(payload.get("scale_to_zero"), True),
        idle_timeout_seconds=_int(payload.get("idle_timeout_seconds"), 300),
        max_hourly_budget_usd=_float(payload.get("max_hourly_budget_usd"), 1.0),
        max_daily_budget_usd=_float(payload.get("max_daily_budget_usd"), 5.0),
        prefer_spot=_bool(payload.get("prefer_spot"), True),
        batch_small_jobs=_bool(payload.get("batch_small_jobs"), True),
    )


def _int(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _float(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _bool(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
