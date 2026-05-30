"""Server-rendered control dashboard pages."""

from django.contrib import messages
from django.db.models import Count, QuerySet
from pathlib import Path

from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from monitoring.catalog_sync import ensure_catalogs_synced_if_enabled
from monitoring.cloud.budget import approve_cloud_job, block_cloud_job, get_budget_summary
from monitoring.dashboard_table_data import (
    artifacts_table,
    budget_summaries_table,
    jobs_table,
    latest_artifacts_table,
    locks_table,
    manifest_jobs_table,
    preview_table,
    recent_jobs_table,
    resource_snapshots_table,
    workers_table,
)
from monitoring.dashboard_models import (
    CloudBudgetPolicy,
    ComputeProfileConfig,
    ComputeResourceSnapshot,
    PipelineJob,
)
from monitoring.models import ExportArtifact
from monitoring.orchestration.job_templates import (
    TEMPLATE_TASKS,
    create_dashboard_jobs,
    preview_template_jobs,
)
from monitoring.orchestration.profile_config import sync_default_profile_configs
from monitoring.orchestration.scheduler import (
    cancel_job,
    pause_job,
    resume_job,
    retry_job,
)
from monitoring.orchestration.snapshots import capture_resource_snapshot
from monitoring.orchestration.worker_state import stop_stale_workers
from monitoring.orchestration_models import ResourceLock, WorkerHeartbeat


class ControlDashboardView(TemplateView):
    """Show queue, resource, budget, and artifact status cards."""

    template_name = "monitoring/control_dashboard.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add dashboard control summary.

        Example:
            Django calls this for `/dashboard/`.
        """
        ensure_catalogs_synced_if_enabled()
        sync_default_profile_configs()
        context = super().get_context_data(**kwargs)
        context["job_counts"] = _job_counts()
        recent_jobs = PipelineJob.objects.select_related("profile")[:10]
        latest_artifacts = ExportArtifact.objects.all()[:5]
        context["recent_jobs"] = recent_jobs
        context["latest_artifacts"] = latest_artifacts
        context["recent_jobs_table"] = recent_jobs_table(recent_jobs)
        context["latest_artifacts_table"] = latest_artifacts_table(latest_artifacts)
        context["latest_snapshot"] = ComputeResourceSnapshot.objects.first()
        budget_summaries = _budget_summaries()
        context["budget_summaries"] = budget_summaries
        context["budget_summaries_table"] = budget_summaries_table(budget_summaries)
        return context


class ProfileConfigListView(ListView):
    """List editable compute profile configuration rows."""

    model = ComputeProfileConfig
    template_name = "monitoring/control_profiles.html"
    context_object_name = "profiles"

    def get_queryset(self) -> QuerySet[ComputeProfileConfig]:
        """Return profile configs after syncing defaults.

        Example:
            Django calls this for `/dashboard/profiles/`.
        """
        sync_default_profile_configs()
        return self.model.objects.all()


class ResourceSnapshotListView(ListView):
    """List captured resource snapshots."""

    model = ComputeResourceSnapshot
    paginate_by = 50
    template_name = "monitoring/control_resources.html"
    context_object_name = "snapshots"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add reusable table payload for resource snapshots.

        Example:
            Django calls this for `/dashboard/resources/`.
        """
        context = super().get_context_data(**kwargs)
        context["snapshots_table"] = resource_snapshots_table(context["snapshots"])
        return context


class PipelineJobListView(ListView):
    """List dashboard jobs with queue filters."""

    model = PipelineJob
    paginate_by = 50
    template_name = "monitoring/control_jobs.html"
    context_object_name = "jobs"

    def get_queryset(self) -> QuerySet[PipelineJob]:
        """Return filtered dashboard jobs.

        Example:
            Django calls this for `/dashboard/jobs/?status=queued`.
        """
        queryset = self.model.objects.select_related("profile")
        return _filter_jobs(queryset, self.request)

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add reusable table payload for filtered jobs.

        Example:
            Django calls this for `/dashboard/jobs/`.
        """
        context = super().get_context_data(**kwargs)
        context["jobs_table"] = jobs_table(context["jobs"])
        return context


class PipelineJobDetailView(DetailView):
    """Show job parameters, logs, events, and manifests."""

    model = PipelineJob
    template_name = "monitoring/control_job_detail.html"
    context_object_name = "job"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add events and log tail.

        Example:
            Django calls this for `/dashboard/jobs/1/`.
        """
        context = super().get_context_data(**kwargs)
        context["events"] = self.object.run_events.all()[:100]
        context["log_text"] = _job_log_text(self.object)
        return context


class CloudBudgetView(TemplateView):
    """Show budget policies, summaries, and blocked cloud jobs."""

    template_name = "monitoring/control_cloud_budget.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add budget policy rows and blocked jobs.

        Example:
            Django calls this for `/dashboard/cloud-budget/`.
        """
        context = super().get_context_data(**kwargs)
        context["policies"] = CloudBudgetPolicy.objects.all()
        summaries = _budget_summaries()
        context["summaries"] = summaries
        context["summaries_table"] = budget_summaries_table(summaries)
        context["waiting_jobs"] = PipelineJob.objects.filter(
            status=PipelineJob.Status.WAITING_APPROVAL
        )
        context["blocked_jobs"] = PipelineJob.objects.filter(
            status=PipelineJob.Status.WAITING_BUDGET
        )
        return context


class ArtifactDashboardView(TemplateView):
    """Show export artifacts plus job manifests."""

    template_name = "monitoring/control_artifacts.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add artifacts and jobs with manifests.

        Example:
            Django calls this for `/dashboard/artifacts/`.
        """
        context = super().get_context_data(**kwargs)
        artifacts = ExportArtifact.objects.all()[:100]
        manifest_jobs = PipelineJob.objects.exclude(manifest_path="")[:100]
        context["artifacts"] = artifacts
        context["manifest_jobs"] = manifest_jobs
        context["artifacts_table"] = artifacts_table(artifacts)
        context["manifest_jobs_table"] = manifest_jobs_table(manifest_jobs)
        return context


class WorkerDashboardView(TemplateView):
    """Show worker heartbeat and active lock state."""

    template_name = "monitoring/control_workers.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add worker rows, locks, and start commands.

        Example:
            Django calls this for `/dashboard/workers/`.
        """
        context = super().get_context_data(**kwargs)
        workers = WorkerHeartbeat.objects.all()
        locks = ResourceLock.objects.select_related("job")
        context["workers"] = workers
        context["locks"] = locks
        context["workers_table"] = workers_table(workers)
        context["locks_table"] = locks_table(locks)
        context["commands"] = _worker_commands()
        return context


def pipeline_plan_view(request: HttpRequest) -> HttpResponse:
    """Preview or create jobs from dashboard templates.

    Example:
        `POST /dashboard/pipeline-plan/`
    """
    context: dict[str, object] = {"templates": sorted(TEMPLATE_TASKS)}
    if request.method == "POST":
        context.update(_pipeline_plan_post(request))
    return render(request, "monitoring/control_pipeline_plan.html", context)


@require_POST
def update_profile_action(request: HttpRequest, pk: int) -> HttpResponseRedirect:
    """Update basic profile limits from the dashboard.

    Example:
        `POST /dashboard/profiles/1/update/`
    """
    profile = get_object_or_404(ComputeProfileConfig, pk=pk)
    _update_profile(profile, request)
    messages.success(request, f"Updated {profile.name}")
    return redirect("monitoring:control-profiles")


@require_POST
def refresh_resources_action(request: HttpRequest) -> HttpResponseRedirect:
    """Capture a new resource snapshot.

    Example:
        `POST /dashboard/resources/refresh/`
    """
    profile = request.POST.get("profile", "")
    capture_resource_snapshot(profile)
    messages.success(request, "Resource snapshot captured")
    return redirect("monitoring:control-resources")


@require_POST
def job_action(request: HttpRequest, pk: int, action: str) -> HttpResponseRedirect:
    """Run a dashboard job action.

    Example:
        `POST /dashboard/jobs/1/cancel/`
    """
    if action == "cancel":
        cancel_job(pk)
    elif action == "pause":
        pause_job(pk)
    elif action == "resume":
        resume_job(pk)
    elif action == "retry":
        retry_job(pk)
    elif action == "approve":
        _approve_job_from_request(request, pk)
    elif action == "block":
        block_cloud_job(PipelineJob.objects.get(pk=pk), "Blocked from dashboard")
    else:
        raise ValueError(f"Invalid job action {action!r}; expected known action")
    messages.success(request, f"Job {pk} action {action} applied")
    return redirect("monitoring:control-job-detail", pk=pk)


def job_manifest_download(request: HttpRequest, pk: int) -> FileResponse:
    """Download a job manifest file.

    Example:
        `GET /dashboard/jobs/1/manifest/`
    """
    job = get_object_or_404(PipelineJob, pk=pk)
    path = Path(job.manifest_path)
    if not job.manifest_path or not path.exists():
        raise Http404(f"Missing manifest for job {pk}; expected existing file")
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


@require_POST
def stop_stale_workers_action(request: HttpRequest) -> HttpResponseRedirect:
    """Mark stale worker rows stopped.

    Example:
        `POST /dashboard/workers/stop-stale/`
    """
    count = stop_stale_workers()
    messages.success(request, f"Marked {count} stale workers stopped")
    return redirect("monitoring:control-workers")


def _pipeline_plan_post(request: HttpRequest) -> dict[str, object]:
    template = request.POST.get("template", "local_simple_pipeline")
    profile = request.POST.get("profile", "local_cpu_low")
    partition = request.POST.get("partition", "monthly")
    provider = request.POST.get("provider", "provider_neutral")
    if request.POST.get("create"):
        if template.startswith("cloud_"):
            _upsert_budget_policy_from_request(request, profile, provider)
        result = create_dashboard_jobs(template, profile, False, partition, provider)
        messages.success(request, f"Created {len(result['job_ids'])} jobs")
        return {"result": result}
    preview = preview_template_jobs(template, profile, partition, provider)
    return {
        "preview": preview,
        "preview_table": preview_table(preview),
        "selected_template": template,
        "selected_profile": profile,
    }


def _filter_jobs(
    queryset: QuerySet[PipelineJob],
    request: HttpRequest,
) -> QuerySet[PipelineJob]:
    queryset = _filter_job_field(queryset, "status", request.GET.get("status", ""))
    queryset = _filter_job_field(queryset, "backend", request.GET.get("backend", ""))
    task = request.GET.get("task", "")
    if task:
        queryset = queryset.filter(task_name__icontains=task)
    profile = request.GET.get("profile", "")
    if profile:
        queryset = queryset.filter(profile__profile_type=profile)
    return queryset.order_by("priority", "-created_at")


def _filter_job_field(
    queryset: QuerySet[PipelineJob],
    field_name: str,
    value: str,
) -> QuerySet[PipelineJob]:
    if not value:
        return queryset
    return queryset.filter(**{field_name: value})


def _job_counts() -> dict[str, int]:
    rows = PipelineJob.objects.values("status").annotate(total=Count("id"))
    return {str(row["status"]): int(row["total"]) for row in rows}


def _budget_summaries() -> list[dict[str, object]]:
    return [get_budget_summary(policy) for policy in CloudBudgetPolicy.objects.all()]


def _job_log_text(job: PipelineJob) -> str:
    from monitoring.orchestration.logging import read_log_tail

    return read_log_tail(job)


def _update_profile(profile: ComputeProfileConfig, request: HttpRequest) -> None:
    profile.enabled = _post_bool(request, "enabled")
    profile.queue_enabled = _post_bool(request, "queue_enabled")
    profile.cloud_enabled = _post_bool(request, "cloud_enabled")
    profile.max_cpu_workers = _post_int(request, "max_cpu_workers", 1)
    profile.max_gpu_workers = _post_int(request, "max_gpu_workers", 0)
    profile.max_vram_gb = _post_float(request, "max_vram_gb", 0.0)
    profile.default_batch_size = _post_int(request, "default_batch_size", 64)
    profile.max_batch_size = _post_int(request, "max_batch_size", 256)
    profile.default_window = _post_int(request, "default_window", 128)
    profile.max_window = _post_int(request, "max_window", 512)
    profile.default_precision = request.POST.get("default_precision", "float32")
    profile.save()


def _approve_job_from_request(request: HttpRequest, pk: int) -> None:
    job = PipelineJob.objects.get(pk=pk)
    approved_by = request.POST.get("approved_by", "dashboard")
    note = request.POST.get("approval_note", "")
    approve_cloud_job(job, approved_by, note)


def _upsert_budget_policy_from_request(
    request: HttpRequest,
    profile: str,
    provider: str,
) -> None:
    if not request.POST.get("cloud_budget_policy"):
        return
    profile_config = ComputeProfileConfig.objects.filter(profile_type=profile).first()
    policy, _created = CloudBudgetPolicy.objects.get_or_create(
        name=f"{profile} {provider} budget",
        defaults={"provider": provider, "profile": profile_config},
    )
    policy.enabled = True
    policy.provider = provider
    policy.profile = profile_config
    policy.max_job_cost_usd = request.POST.get("max_job_cost_usd", "0") or "0"
    policy.max_daily_cost_usd = request.POST.get("max_daily_cost_usd", "0") or "0"
    policy.max_total_cost_usd = request.POST.get("max_total_cost_usd", "0") or "0"
    policy.max_runtime_hours_per_job = _post_float(request, "max_runtime_hours", 4.0)
    policy.require_manual_approval = _post_bool(request, "require_manual_approval")
    policy.save()


def _post_bool(request: HttpRequest, name: str) -> bool:
    return request.POST.get(name) == "1"


def _post_int(request: HttpRequest, name: str, default: int) -> int:
    value = request.POST.get(name, "")
    return int(value) if value else default


def _post_float(request: HttpRequest, name: str, default: float) -> float:
    value = request.POST.get(name, "")
    return float(value) if value else default


def _worker_commands() -> tuple[str, ...]:
    return (
        "python manage.py dashboard_worker --profile local_cpu_low --worker-id cpu-1",
        "python manage.py dashboard_worker --profile local_mx350_queue --worker-id mx350-1",
        "python manage.py dashboard_worker --profile local_rtx4060ti --worker-id gpu-1",
    )
