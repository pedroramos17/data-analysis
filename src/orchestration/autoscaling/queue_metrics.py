"""Queue metric snapshots for autoscaling decisions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SMALL_JOB_RUNTIME_SECONDS = 10 * 60
SMALL_JOB_DATASET_GB = 2.0
GPU_MODEL_HINTS = ("mamba", "samba", "tcn", "gru", "attention", "transformer")


@dataclass(frozen=True, slots=True)
class QueuedJob:
    """Queued training or inference job signal for autoscaling."""

    job_id: str
    task_type: str = "training"
    model_type: str = "baseline"
    estimated_runtime_seconds: int = 0
    dataset_size_gb: float = 0.0
    gpu_memory_gb: int = 0
    requires_gpu: bool = False
    window_count: int = 1
    failure_rate: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> QueuedJob:
        """Build a queued-job signal from a provider-neutral payload."""
        model_type = str(payload.get("model_type") or payload.get("model_name") or "baseline")
        return cls(
            job_id=str(payload.get("job_id") or payload.get("id") or payload.get("name") or "queued-job"),
            task_type=str(payload.get("task_type") or payload.get("task") or "training"),
            model_type=model_type,
            estimated_runtime_seconds=_int(payload.get("estimated_runtime_seconds") or payload.get("runtime_seconds"), 0),
            dataset_size_gb=_float(payload.get("dataset_size_gb"), 0.0),
            gpu_memory_gb=_int(payload.get("gpu_memory_gb") or payload.get("min_gpu_memory_gb"), 0),
            requires_gpu=_bool(payload.get("requires_gpu"), _model_prefers_gpu(model_type)),
            window_count=_int(payload.get("window_count"), 1),
            failure_rate=_float(payload.get("failure_rate"), 0.0),
            payload=dict(payload),
        )

    def prefers_gpu(self) -> bool:
        """Return whether this job should be routed to GPU."""
        return self.requires_gpu or self.gpu_memory_gb > 0 or _model_prefers_gpu(self.model_type)

    def is_small(self) -> bool:
        """Return whether this job is cheap enough to prefer CPU/local."""
        runtime = self.estimated_runtime_seconds or SMALL_JOB_RUNTIME_SECONDS
        return runtime <= SMALL_JOB_RUNTIME_SECONDS and self.dataset_size_gb <= SMALL_JOB_DATASET_GB and self.gpu_memory_gb <= 8


@dataclass(frozen=True, slots=True)
class ActivePod:
    """Active GPU pod signal for autoscaling."""

    pod_id: str
    status: str = "RUNNING"
    running_jobs: int = 0
    hourly_cost_usd: float = 0.0
    last_active_at: datetime | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> ActivePod:
        """Build an active-pod signal from a provider response or test fixture."""
        return cls(
            pod_id=str(payload.get("pod_id") or payload.get("job_id") or payload.get("id") or "pod"),
            status=str(payload.get("status") or "RUNNING"),
            running_jobs=_int(payload.get("running_jobs"), 0),
            hourly_cost_usd=_float(payload.get("hourly_cost_usd"), 0.0),
            last_active_at=_datetime(payload.get("last_active_at")),
        )

    def is_idle(self, now: datetime, idle_timeout_seconds: int) -> bool:
        """Return whether this pod exceeded the idle timeout."""
        if self.running_jobs > 0 or self.last_active_at is None:
            return False
        active_at = self.last_active_at
        if active_at.tzinfo is None:
            active_at = active_at.replace(tzinfo=UTC)
        return (now - active_at).total_seconds() >= idle_timeout_seconds


@dataclass(frozen=True, slots=True)
class QueueMetrics:
    """Point-in-time queue and pod metrics used by autoscaling."""

    queued_jobs: tuple[QueuedJob, ...] = ()
    active_pods: tuple[ActivePod, ...] = ()
    budget_spent_today_usd: float = 0.0
    current_hourly_spend_usd: float = 0.0
    failure_rate: float = 0.0
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payloads(
        cls,
        queued_jobs: Iterable[Mapping[str, object] | QueuedJob] = (),
        active_pods: Iterable[Mapping[str, object] | ActivePod] = (),
        *,
        budget_spent_today_usd: float = 0.0,
        current_hourly_spend_usd: float = 0.0,
        failure_rate: float = 0.0,
    ) -> QueueMetrics:
        """Build metrics from simple mappings."""
        jobs = tuple(job if isinstance(job, QueuedJob) else QueuedJob.from_mapping(job) for job in queued_jobs)
        pods = tuple(pod if isinstance(pod, ActivePod) else ActivePod.from_mapping(pod) for pod in active_pods)
        return cls(
            queued_jobs=jobs,
            active_pods=pods,
            budget_spent_today_usd=budget_spent_today_usd,
            current_hourly_spend_usd=current_hourly_spend_usd,
            failure_rate=failure_rate,
        )

    @property
    def queue_length(self) -> int:
        """Return total queued jobs."""
        return len(self.queued_jobs)

    @property
    def gpu_queue(self) -> tuple[QueuedJob, ...]:
        """Return queued jobs that prefer GPU execution."""
        return tuple(job for job in self.queued_jobs if job.prefers_gpu())

    @property
    def cpu_queue(self) -> tuple[QueuedJob, ...]:
        """Return queued jobs that should stay CPU/local."""
        return tuple(job for job in self.queued_jobs if not job.prefers_gpu())

    @property
    def active_gpu_pods(self) -> tuple[ActivePod, ...]:
        """Return active GPU pods that count toward concurrency."""
        return tuple(pod for pod in self.active_pods if pod.status.upper() not in {"TERMINATED", "CANCELLED", "FAILED"})

    def max_gpu_memory_needed_gb(self) -> int:
        """Return max GPU memory needed by queued jobs."""
        return max((job.gpu_memory_gb for job in self.gpu_queue), default=0)

    def max_dataset_size_gb(self) -> float:
        """Return max dataset size for queued jobs."""
        return max((job.dataset_size_gb for job in self.queued_jobs), default=0.0)

    def estimated_gpu_runtime_seconds(self) -> int:
        """Return summed runtime for GPU-preferring queued jobs."""
        return sum(max(job.estimated_runtime_seconds, 0) for job in self.gpu_queue)


def _model_prefers_gpu(model_type: str) -> bool:
    normalized = model_type.lower()
    return any(hint in normalized for hint in GPU_MODEL_HINTS)


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


def _datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
