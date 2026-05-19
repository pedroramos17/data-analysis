"""Table payload builders for server-rendered dashboards."""

from collections.abc import Iterable, Mapping

from django.urls import reverse

from monitoring.templatetags.dashboard_tables import (
    DashboardTable,
    DashboardTableCell,
    DashboardTableColumn,
    link_cell,
    text_cell,
)


def recent_jobs_table(jobs: Iterable[object]) -> DashboardTable:
    """Return the Compute Control Dashboard recent jobs table.

    Example:
        `table = recent_jobs_table(PipelineJob.objects.all())`
    """
    columns = _columns(("job", "Job"), ("status", "Status"), ("profile", "Profile"), ("progress", "Progress"))
    rows = tuple(_recent_job_row(job) for job in jobs)
    return DashboardTable("recent-jobs", columns, rows, "No dashboard jobs yet.")


def latest_artifacts_table(artifacts: Iterable[object]) -> DashboardTable:
    """Return a compact artifact table for dashboard cards.

    Example:
        `table = latest_artifacts_table(ExportArtifact.objects.all())`
    """
    columns = _columns(("path", "Path"), ("rows", "Rows"))
    rows = tuple(_artifact_row(artifact, with_created=False) for artifact in artifacts)
    return DashboardTable("latest-artifacts", columns, rows, "No artifacts yet.")


def budget_summaries_table(summaries: Iterable[Mapping[str, object]]) -> DashboardTable:
    """Return a reusable cloud budget summary table.

    Example:
        `table = budget_summaries_table(summaries)`
    """
    columns = _columns(("policy", "Policy"), ("used", "Estimated used"), ("remaining", "Remaining total"), ("waiting", "Waiting approval"))
    rows = tuple(_budget_row(summary) for summary in summaries)
    return DashboardTable("cloud-budget-summary", columns, rows, "No budget policies yet.")


def jobs_table(jobs: Iterable[object]) -> DashboardTable:
    """Return the dashboard jobs list table.

    Example:
        `table = jobs_table(PipelineJob.objects.all())`
    """
    columns = _columns(("job", "Job"), ("task", "Task"), ("status", "Status"), ("profile", "Profile"), ("backend", "Backend"), ("progress", "Progress"), ("created", "Created"))
    rows = tuple(_job_row(job) for job in jobs)
    return DashboardTable("dashboard-jobs", columns, rows, "No jobs found.")


def resource_snapshots_table(snapshots: Iterable[object]) -> DashboardTable:
    """Return the compute resource snapshots table.

    Example:
        `table = resource_snapshots_table(snapshots)`
    """
    columns = _columns(("host", "Host"), ("cpu", "CPU"), ("ram", "RAM GB"), ("gpu", "GPU"), ("vram", "VRAM GB"), ("torch", "Torch"), ("cupy", "CuPy"), ("native", "Native"), ("captured", "Captured"))
    rows = tuple(_snapshot_row(snapshot) for snapshot in snapshots)
    return DashboardTable("resource-snapshots", columns, rows, "No resource snapshots yet.")


def workers_table(workers: Iterable[object]) -> DashboardTable:
    """Return worker heartbeat rows for the worker dashboard.

    Example:
        `table = workers_table(WorkerHeartbeat.objects.all())`
    """
    columns = _columns(("worker", "Worker"), ("profile", "Profile"), ("backend", "Backend"), ("status", "Status"), ("job", "Current job"), ("heartbeat", "Heartbeat"))
    rows = tuple(_worker_row(worker) for worker in workers)
    return DashboardTable("worker-heartbeats", columns, rows, "No workers registered.")


def locks_table(locks: Iterable[object]) -> DashboardTable:
    """Return active resource lock rows.

    Example:
        `table = locks_table(ResourceLock.objects.all())`
    """
    columns = _columns(("resource", "Resource"), ("worker", "Worker"), ("job", "Job"), ("heartbeat", "Heartbeat"), ("expires", "Expires"))
    rows = tuple(_lock_row(lock) for lock in locks)
    return DashboardTable("resource-locks", columns, rows, "No active resource locks.")


def artifacts_table(artifacts: Iterable[object]) -> DashboardTable:
    """Return the control artifacts table.

    Example:
        `table = artifacts_table(ExportArtifact.objects.all())`
    """
    columns = _columns(("path", "Path"), ("type", "Type"), ("rows", "Rows"), ("created", "Created"))
    rows = tuple(_artifact_row(artifact, with_created=True) for artifact in artifacts)
    return DashboardTable("control-artifacts", columns, rows, "No artifacts yet.")


def manifest_jobs_table(jobs: Iterable[object]) -> DashboardTable:
    """Return jobs with manifest links.

    Example:
        `table = manifest_jobs_table(PipelineJob.objects.exclude(manifest_path=""))`
    """
    columns = _columns(("job", "Job"), ("task", "Task"), ("manifest", "Manifest"))
    rows = tuple(_manifest_job_row(job) for job in jobs)
    return DashboardTable("manifest-jobs", columns, rows, "No job manifests yet.")


def metrics_table(metrics: Iterable[object]) -> DashboardTable:
    """Return recent NLP metric rows.

    Example:
        `table = metrics_table(NlpRunMetric.objects.all())`
    """
    columns = _columns(("entrypoint", "Entrypoint"), ("runtime", "Runtime"), ("tokens", "Tokens"), ("created", "Created"))
    rows = tuple(_metric_row(metric) for metric in metrics)
    return DashboardTable("recent-nlp-costs", columns, rows, "No NLP runs yet.")


def exports_table(artifacts: Iterable[object]) -> DashboardTable:
    """Return recent exports for the Operations Dashboard.

    Example:
        `table = exports_table(ExportArtifact.objects.all())`
    """
    columns = _columns(("path", "Path"), ("rows", "Rows"), ("created", "Created"))
    rows = tuple(_export_row(artifact) for artifact in artifacts)
    return DashboardTable("recent-exports", columns, rows, "No exports yet.")


def preview_table(previews: Iterable[object]) -> DashboardTable:
    """Return a pipeline plan preview table.

    Example:
        `table = preview_table(result.preview)`
    """
    columns = _columns(("task", "Task"), ("profile", "Profile"), ("backend", "Backend"), ("cost", "Cost"))
    rows = tuple(_preview_row(preview) for preview in previews)
    return DashboardTable("pipeline-preview", columns, rows, "No preview rows.")


def _columns(*pairs: tuple[str, str]) -> tuple[DashboardTableColumn, ...]:
    return tuple(DashboardTableColumn(key, label) for key, label in pairs)


def _recent_job_row(job: object) -> tuple[DashboardTableCell, ...]:
    href = reverse("monitoring:control-job-detail", args=[job.pk])
    return (link_cell(job.job_name, href), text_cell(job.status), text_cell(job.profile.profile_type), text_cell(_percent(job.progress_percent)))


def _job_row(job: object) -> tuple[DashboardTableCell, ...]:
    href = reverse("monitoring:control-job-detail", args=[job.pk])
    return (link_cell(job.job_name, href), text_cell(job.task_name), text_cell(job.status), text_cell(job.profile.profile_type), text_cell(job.backend), text_cell(_percent(job.progress_percent)), text_cell(_date(job.created_at), "muted"))


def _artifact_row(artifact: object, with_created: bool) -> tuple[DashboardTableCell, ...]:
    href = reverse("monitoring:export-artifact-detail", args=[artifact.pk])
    base = (link_cell(artifact.path, href), text_cell(artifact.row_count))
    if not with_created:
        return base
    return (link_cell(artifact.path, href), text_cell(artifact.export_type), text_cell(artifact.row_count), text_cell(_date(artifact.created_at), "muted"))


def _budget_row(summary: Mapping[str, object]) -> tuple[DashboardTableCell, ...]:
    return (text_cell(summary.get("policy", "")), text_cell(f"${summary.get('estimated_used_usd', 0)}"), text_cell(f"${summary.get('remaining_total_usd', 0)}"), text_cell(summary.get("jobs_waiting_approval", 0)))


def _snapshot_row(snapshot: object) -> tuple[DashboardTableCell, ...]:
    return (text_cell(snapshot.hostname), text_cell(snapshot.cpu_count), text_cell(snapshot.ram_total_gb), text_cell(snapshot.gpu_name or "none"), text_cell(snapshot.gpu_total_vram_gb or 0), text_cell(snapshot.torch_available), text_cell(snapshot.cupy_available), text_cell(snapshot.native_ctypes_available), text_cell(_date(snapshot.captured_at), "muted"))


def _worker_row(worker: object) -> tuple[DashboardTableCell, ...]:
    job_name = worker.current_job.job_name if worker.current_job else ""
    return (text_cell(worker.worker_id), text_cell(worker.profile), text_cell(worker.backend), text_cell(worker.status), text_cell(job_name), text_cell(_date(worker.last_heartbeat_at), "muted"))


def _lock_row(lock: object) -> tuple[DashboardTableCell, ...]:
    job_name = lock.job.job_name if lock.job else ""
    return (text_cell(lock.resource_name), text_cell(lock.locked_by_worker), text_cell(job_name), text_cell(_date(lock.heartbeat_at), "muted"), text_cell(_date(lock.expires_at), "muted"))


def _manifest_job_row(job: object) -> tuple[DashboardTableCell, ...]:
    href = reverse("monitoring:control-job-manifest", args=[job.pk])
    return (text_cell(job.job_name), text_cell(job.task_name), link_cell(job.manifest_path, href))


def _metric_row(metric: object) -> tuple[DashboardTableCell, ...]:
    return (text_cell(metric.entrypoint), text_cell(f"{metric.total_ms:.2f} ms"), text_cell(metric.token_count), text_cell(_date(metric.created_at), "muted"))


def _export_row(artifact: object) -> tuple[DashboardTableCell, ...]:
    href = reverse("monitoring:export-artifact-detail", args=[artifact.pk])
    return (link_cell(artifact.path, href), text_cell(artifact.row_count), text_cell(_date(artifact.created_at), "muted"))


def _preview_row(preview: object) -> tuple[DashboardTableCell, ...]:
    return (text_cell(preview.task_name), text_cell(preview.profile), text_cell(preview.backend), text_cell(preview.estimated_cost_usd))


def _date(value: object) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M")


def _percent(value: object) -> str:
    return f"{float(value):.1f}%"
