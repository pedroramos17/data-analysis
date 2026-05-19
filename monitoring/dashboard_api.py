"""Internal JSON API for dashboard refresh and automation."""

from decimal import Decimal
import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from monitoring.cloud.budget import (
    apply_budget_guard,
    approve_cloud_job,
    get_budget_summary,
    policy_for_job,
)
from monitoring.dashboard_models import (
    CloudBudgetPolicy,
    ComputeProfileConfig,
    ComputeResourceSnapshot,
    JobRunEvent,
    PipelineJob,
)
from monitoring.models import ExportArtifact
from monitoring.orchestration.logging import read_log_tail
from monitoring.orchestration.profile_config import sync_default_profile_configs
from monitoring.orchestration.scheduler import (
    cancel_job,
    enqueue_job,
    pause_job,
    resume_job,
    retry_job,
)
from monitoring.orchestration.snapshots import capture_resource_snapshot


@require_GET
def dashboard_status_api(request: HttpRequest) -> JsonResponse:
    """Return grouped queue, resource, budget, and artifact status.

    Example:
        `GET /api/dashboard/status/`
    """
    sync_default_profile_configs()
    return JsonResponse(
        {
            "jobs": _job_status_counts(),
            "active_profiles": _active_profiles(),
            "current_resources": _latest_resource_payload(),
            "cloud_budget_summary": _budget_payloads(),
            "latest_artifacts": _artifact_payloads(),
        }
    )


@require_http_methods(["GET", "POST"])
def dashboard_jobs_api(request: HttpRequest) -> JsonResponse:
    """List or create dashboard jobs.

    Example:
        `POST /api/dashboard/jobs/`
    """
    if request.method == "GET":
        return JsonResponse({"jobs": [_job_payload(job) for job in _filtered_jobs(request)]})
    try:
        payload = _json_body(request)
        _validate_job_payload(payload)
        job = enqueue_job(
            str(payload["task_name"]),
            str(payload["profile"]),
            str(payload.get("backend", "cpu")),
            _job_params_from_payload(payload),
        )
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    if job.backend == "cloud":
        apply_budget_guard(job, policy_for_job(job))
    return JsonResponse({"job": _job_payload(job)}, status=201)


@require_POST
def dashboard_job_action_api(
    request: HttpRequest,
    pk: int,
    action: str,
) -> JsonResponse:
    """Apply one job state transition.

    Example:
        `POST /api/dashboard/jobs/1/cancel/`
    """
    if action == "cancel":
        job = cancel_job(pk)
    elif action == "pause":
        job = pause_job(pk)
    elif action == "resume":
        job = resume_job(pk)
    elif action == "retry":
        job = retry_job(pk)
    elif action == "approve":
        job = approve_cloud_job(PipelineJob.objects.get(pk=pk), "api")
    else:
        return JsonResponse({"error": f"Invalid action {action}"}, status=400)
    return JsonResponse({"job": _job_payload(job)})


@require_GET
def dashboard_job_events_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Return recent events for a job.

    Example:
        `GET /api/dashboard/jobs/1/events/`
    """
    job = PipelineJob.objects.get(pk=pk)
    events = [_event_payload(event) for event in job.run_events.all()[:200]]
    return JsonResponse({"events": events})


@require_GET
def dashboard_job_logs_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Return log text for a job.

    Example:
        `GET /api/dashboard/jobs/1/logs/`
    """
    job = PipelineJob.objects.get(pk=pk)
    return JsonResponse({"log": read_log_tail(job)})


@require_GET
def dashboard_resources_api(request: HttpRequest) -> JsonResponse:
    """Return recent resource snapshots.

    Example:
        `GET /api/dashboard/resources/`
    """
    snapshots = ComputeResourceSnapshot.objects.all()[:20]
    return JsonResponse({"resources": [_snapshot_payload(item) for item in snapshots]})


@require_POST
def dashboard_resources_refresh_api(request: HttpRequest) -> JsonResponse:
    """Capture and return a fresh resource snapshot.

    Example:
        `POST /api/dashboard/resources/refresh/`
    """
    snapshot = capture_resource_snapshot()
    return JsonResponse({"resource": _snapshot_payload(snapshot)}, status=201)


@require_GET
def dashboard_budget_api(request: HttpRequest) -> JsonResponse:
    """Return budget summaries for all policies.

    Example:
        `GET /api/dashboard/budget/`
    """
    return JsonResponse({"summaries": _budget_payloads()})


@require_POST
def dashboard_budget_policy_update_api(
    request: HttpRequest,
    pk: int,
) -> JsonResponse:
    """Update one budget policy from JSON fields.

    Example:
        `POST /api/dashboard/budget/policies/1/update/`
    """
    payload = _json_body(request)
    policy = CloudBudgetPolicy.objects.get(pk=pk)
    _update_policy(policy, payload)
    return JsonResponse({"summary": get_budget_summary(policy)})


def _json_body(request: HttpRequest) -> dict[str, object]:
    try:
        value = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as error:
        raise ValueError("Invalid JSON body; expected object") from error
    if not isinstance(value, dict):
        raise ValueError(f"Invalid JSON body {value!r}; expected object")
    return value


def _job_params_from_payload(payload: dict[str, object]) -> dict[str, object]:
    params = payload.get("params", {})
    if not isinstance(params, dict):
        raise ValueError(f"Invalid params {params!r}; expected object")
    params["priority"] = payload.get("priority", 100)
    return params


def _validate_job_payload(payload: dict[str, object]) -> None:
    for field_name in ("task_name", "profile"):
        if field_name not in payload:
            raise ValueError(f"Invalid job payload {payload!r}; expected {field_name}")
    params = payload.get("params", {})
    if not isinstance(params, dict) or "command" not in params:
        raise ValueError(f"Invalid job params {params!r}; expected command")


def _filtered_jobs(request: HttpRequest) -> list[PipelineJob]:
    queryset = PipelineJob.objects.select_related("profile").all()
    for field_name in ("status", "backend"):
        value = request.GET.get(field_name, "")
        if value:
            queryset = queryset.filter(**{field_name: value})
    profile = request.GET.get("profile", "")
    if profile:
        queryset = queryset.filter(profile__profile_type=profile)
    task = request.GET.get("task", "")
    if task:
        queryset = queryset.filter(task_name__icontains=task)
    return list(queryset.order_by("priority", "-created_at")[:200])


def _job_payload(job: PipelineJob) -> dict[str, object]:
    return {
        "id": job.pk,
        "job_name": job.job_name,
        "task_name": job.task_name,
        "profile": job.profile.profile_type,
        "backend": job.backend,
        "status": job.status,
        "priority": job.priority,
        "progress_percent": job.progress_percent,
        "estimated_cost_usd": str(job.estimated_cost_usd),
        "actual_cost_usd": str(job.actual_cost_usd),
        "manifest_path": job.manifest_path,
        "log_path": job.log_path,
    }


def _event_payload(event: JobRunEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "message": event.message,
        "payload": event.payload_json,
        "created_at": event.created_at.isoformat(),
    }


def _snapshot_payload(snapshot: ComputeResourceSnapshot | None) -> dict[str, object]:
    if snapshot is None:
        return {}
    return {
        "hostname": snapshot.hostname,
        "cpu_count": snapshot.cpu_count,
        "ram_total_gb": snapshot.ram_total_gb,
        "gpu_available": snapshot.gpu_available,
        "gpu_name": snapshot.gpu_name,
        "gpu_total_vram_gb": snapshot.gpu_total_vram_gb,
        "cuda_available": snapshot.cuda_available,
        "torch_available": snapshot.torch_available,
        "cupy_available": snapshot.cupy_available,
        "captured_at": snapshot.captured_at.isoformat(),
    }


def _active_profiles() -> list[dict[str, object]]:
    profiles = ComputeProfileConfig.objects.filter(enabled=True)
    return [{"name": profile.name, "type": profile.profile_type} for profile in profiles]


def _latest_resource_payload() -> dict[str, object]:
    return _snapshot_payload(ComputeResourceSnapshot.objects.first())


def _budget_payloads() -> list[dict[str, object]]:
    return [get_budget_summary(policy) for policy in CloudBudgetPolicy.objects.all()]


def _artifact_payloads() -> list[dict[str, object]]:
    artifacts = ExportArtifact.objects.all()[:10]
    return [
        {
            "id": artifact.pk,
            "export_type": artifact.export_type,
            "path": artifact.path,
            "row_count": artifact.row_count,
            "created_at": artifact.created_at.isoformat(),
        }
        for artifact in artifacts
    ]


def _job_status_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for status, _label in PipelineJob.Status.choices:
        counts[status] = PipelineJob.objects.filter(status=status).count()
    return counts


def _update_policy(
    policy: CloudBudgetPolicy,
    payload: dict[str, object],
) -> None:
    for field_name in _policy_decimal_fields():
        if field_name in payload:
            setattr(policy, field_name, Decimal(str(payload[field_name])))
    if "require_manual_approval" in payload:
        policy.require_manual_approval = bool(payload["require_manual_approval"])
    if "enabled" in payload:
        policy.enabled = bool(payload["enabled"])
    policy.save()


def _policy_decimal_fields() -> tuple[str, ...]:
    return (
        "max_total_cost_usd",
        "max_daily_cost_usd",
        "max_job_cost_usd",
    )
