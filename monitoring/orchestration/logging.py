"""Job event and log-file helpers for dashboard orchestration."""

from pathlib import Path
import re

from django.conf import settings

from monitoring.dashboard_models import JobRunEvent, PipelineJob


PROGRESS_PATTERN = re.compile(r"^PROGRESS\s+(\d+)\s*/\s*(\d+)\s*$")


def append_job_event(
    job: PipelineJob,
    event_type: str,
    message: str,
    payload: dict[str, object] | None = None,
) -> JobRunEvent:
    """Append one execution event to a pipeline job.

    Example:
        `append_job_event(job, "queued", "Ready")`
    """
    return JobRunEvent.objects.create(
        job=job,
        event_type=event_type,
        message=message,
        payload_json=payload or {},
    )


def ensure_job_log_path(job: PipelineJob) -> Path:
    """Return and persist the log path for a job.

    Example:
        `path = ensure_job_log_path(job)`
    """
    if job.log_path:
        return Path(job.log_path)
    path = _job_log_dir() / f"job_{job.pk}.log"
    job.log_path = str(path)
    job.save(update_fields=["log_path", "updated_at"])
    return path


def append_log_line(job: PipelineJob, stream_name: str, line: str) -> None:
    """Append one timestamp-free line to a job log file.

    Example:
        `append_log_line(job, "stdout", "PROGRESS 1/2")`
    """
    path = ensure_job_log_path(job)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{stream_name}] {line.rstrip()}\n")


def read_log_tail(job: PipelineJob, max_lines: int = 200) -> str:
    """Return the latest log lines for a job.

    Example:
        `read_log_tail(job, 50)`
    """
    if not job.log_path:
        return ""
    path = Path(job.log_path)
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[-max_lines:])


def update_progress_from_line(job: PipelineJob, line: str) -> bool:
    """Update job progress when a line has `PROGRESS current/total`.

    Example:
        `update_progress_from_line(job, "PROGRESS 20/100")`
    """
    match = PROGRESS_PATTERN.match(line.strip())
    if not match:
        return False
    current = int(match.group(1))
    total = max(int(match.group(2)), 1)
    percent = round((current / total) * 100, 2)
    _save_progress(job, current, total, percent)
    return True


def _save_progress(job: PipelineJob, current: int, total: int, percent: float) -> None:
    job.progress_current = current
    job.progress_total = total
    job.progress_percent = percent
    job.save(
        update_fields=[
            "progress_current",
            "progress_total",
            "progress_percent",
            "updated_at",
        ]
    )
    append_job_event(
        job,
        "progress",
        f"PROGRESS {current}/{total}",
        {"current": current, "total": total, "percent": percent},
    )


def _job_log_dir() -> Path:
    export_dir = getattr(settings, "PARQUET_EXPORT_DIR", Path("exports"))
    return Path(export_dir) / "dashboard_jobs"
