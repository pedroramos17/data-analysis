"""Per-job operational manifest writers."""

from pathlib import Path
import json

from django.conf import settings

from monitoring.dashboard_models import PipelineJob


def write_job_manifest(
    job: PipelineJob,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    device: str = "",
) -> Path:
    """Write and persist the operational manifest for a job.

    Example:
        `path = write_job_manifest(job, warnings=[], errors=[])`
    """
    path = _manifest_path(job)
    payload = _manifest_payload(job, warnings or [], errors or [], device)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    job.manifest_path = str(path)
    job.save(update_fields=["manifest_path", "updated_at"])
    return path


def _manifest_path(job: PipelineJob) -> Path:
    if job.manifest_path:
        return Path(job.manifest_path)
    export_dir = getattr(settings, "PARQUET_EXPORT_DIR", Path("exports"))
    return Path(export_dir) / "dashboard_jobs" / f"job_{job.pk}_manifest.json"


def _manifest_payload(
    job: PipelineJob,
    warnings: list[str],
    errors: list[str],
    device: str,
) -> dict[str, object]:
    return {
        "job_id": job.pk,
        "job_name": job.job_name,
        "task_name": job.task_name,
        "profile": job.profile.profile_type,
        "backend": job.backend,
        "device": device,
        "parameters": job.parameters_json,
        "inputs": job.input_artifacts_json,
        "outputs": job.output_artifacts_json,
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "status": job.status,
        "duration_seconds": _duration_seconds(job),
        "estimated_cost_usd": str(job.estimated_cost_usd),
        "actual_cost_usd": str(job.actual_cost_usd),
        "warnings": warnings,
        "errors": errors,
        "log_path": job.log_path,
    }


def _duration_seconds(job: PipelineJob) -> int:
    if job.started_at is None or job.finished_at is None:
        return 0
    return max(int((job.finished_at - job.started_at).total_seconds()), 0)


def _iso(value: object) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return ""
