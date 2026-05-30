"""Resource selection for dashboard jobs."""

from monitoring.dashboard_models import ComputeProfileConfig, PipelineJob
from monitoring.orchestration.locks import acquire_lock
from monitoring.orchestration_models import ResourceLock


GPU_BACKENDS = {"gpu", "cuda", "cupy"}


def acquire_job_lock(
    job: PipelineJob,
    worker_id: str,
    ttl_seconds: int = 120,
) -> ResourceLock | None:
    """Acquire the first available resource lock for a job.

    Example:
        `lock = acquire_job_lock(job, "cpu-1")`
    """
    for resource_name in candidate_resource_names(job):
        lock = acquire_lock(resource_name, job, ttl_seconds, worker_id)
        if lock is not None:
            return lock
    return None


def candidate_resource_names(job: PipelineJob) -> tuple[str, ...]:
    """Return possible resource lock names for a job.

    Example:
        `candidate_resource_names(job)` returns CPU or GPU slots.
    """
    profile = job.profile
    if job.backend == "cloud":
        provider = str(job.parameters_json.get("provider", "provider_neutral"))
        return (f"cloud_provider_slot:{provider}",)
    if _needs_gpu(job, profile):
        return (_gpu_resource_name(profile),)
    return _cpu_resource_names(profile)


def _needs_gpu(job: PipelineJob, profile: ComputeProfileConfig) -> bool:
    if job.backend in GPU_BACKENDS:
        return True
    if profile.profile_type == "local_mx350_queue" and "micro" in job.task_name:
        return True
    return profile.profile_type == "local_rtx4060ti" and "_gpu" in job.task_name


def _gpu_resource_name(profile: ComputeProfileConfig) -> str:
    if profile.profile_type == "local_mx350_queue":
        return "mx350_gpu"
    if profile.profile_type == "local_rtx4060ti":
        return "rtx4060ti_gpu"
    return "gpu:0"


def _cpu_resource_names(profile: ComputeProfileConfig) -> tuple[str, ...]:
    slots = max(int(profile.max_cpu_workers), 1)
    return tuple(f"cpu_pool:{slot}" for slot in range(slots))
