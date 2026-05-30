"""Reusable dashboard job templates for local and cloud pipelines."""

from dataclasses import dataclass
from pathlib import Path
from decimal import Decimal

from django.conf import settings

from monitoring.cloud.budget import (
    apply_budget_guard,
    policy_for_job,
    record_estimated_usage,
)
from monitoring.cloud.jobs import create_cloud_job_spec, write_cloud_job_spec
from monitoring.dashboard_models import CloudBudgetPolicy, PipelineJob
from monitoring.orchestration.manifest import write_job_manifest
from monitoring.orchestration.scheduler import enqueue_job


@dataclass(frozen=True, slots=True)
class TemplateJobPreview:
    """One job produced by a dashboard template.

    Example:
        `preview = TemplateJobPreview("task", "profile", "cpu", "python ...")`
    """

    task_name: str
    profile: str
    backend: str
    command: str
    estimated_cost_usd: Decimal


def preview_template_jobs(
    template: str,
    profile: str,
    partition: str = "monthly",
    provider: str = "provider_neutral",
) -> tuple[TemplateJobPreview, ...]:
    """Return jobs a template would create without writing database rows.

    Example:
        `preview_template_jobs("local_simple_pipeline", "local_cpu_low")`
    """
    tasks = _template_tasks(template)
    return tuple(_preview_task(template, task, profile, partition) for task in tasks)


def create_dashboard_jobs(
    template: str,
    profile: str,
    dry_run: bool = False,
    partition: str = "monthly",
    provider: str = "provider_neutral",
) -> dict[str, object]:
    """Create PipelineJob rows from a named template.

    Example:
        `create_dashboard_jobs("local_simple_pipeline", "local_cpu_low")`
    """
    previews = preview_template_jobs(template, profile, partition, provider)
    if dry_run:
        return _template_result(template, previews, ())
    jobs = tuple(_create_job(preview, partition, provider) for preview in previews)
    return _template_result(template, previews, jobs)


def _create_job(
    preview: TemplateJobPreview,
    partition: str,
    provider: str,
) -> PipelineJob:
    params = _job_params(preview, partition, provider)
    job = enqueue_job(preview.task_name, preview.profile, preview.backend, params)
    _after_create_job(job, preview, partition)
    return job


def _after_create_job(
    job: PipelineJob,
    preview: TemplateJobPreview,
    partition: str,
) -> None:
    if preview.backend == "cloud":
        _prepare_cloud_job(job, partition)
        return
    write_job_manifest(job, warnings=[], errors=[])


def _prepare_cloud_job(job: PipelineJob, partition: str) -> None:
    spec = create_cloud_job_spec(job.task_name, job.profile.profile_type, partition)
    spec_path = write_cloud_job_spec(spec, _dashboard_job_dir() / "cloud_specs")
    job.manifest_path = str(spec_path)
    job.input_artifacts_json = dict(spec.inputs)
    job.output_artifacts_json = dict(spec.outputs)
    job.save(
        update_fields=[
            "manifest_path",
            "input_artifacts_json",
            "output_artifacts_json",
            "updated_at",
        ]
    )
    _ensure_template_policy(job)
    record_estimated_usage(job)
    apply_budget_guard(job, policy_for_job(job))


def _ensure_template_policy(job: PipelineJob) -> CloudBudgetPolicy:
    provider = str(job.parameters_json.get("provider", "provider_neutral"))
    policy, _created = CloudBudgetPolicy.objects.get_or_create(
        name=f"{job.profile.profile_type} {provider} budget",
        defaults={
            "enabled": True,
            "provider": provider,
            "profile": job.profile,
            "max_total_cost_usd": "0",
            "max_daily_cost_usd": "0",
            "max_job_cost_usd": "0",
            "allowed_tasks_json": sorted(_cloud_template_tasks()),
            "require_manual_approval": True,
        },
    )
    return policy


def _cloud_template_tasks() -> set[str]:
    tasks: set[str] = set()
    for name, values in TEMPLATE_TASKS.items():
        if name.startswith("cloud_"):
            tasks.update(values)
    return tasks


def _job_params(
    preview: TemplateJobPreview,
    partition: str,
    provider: str,
) -> dict[str, object]:
    return {
        "job_name": f"{preview.task_name}_{preview.profile}",
        "command": preview.command,
        "provider": provider,
        "partition": partition,
        "estimated_cost_usd": str(preview.estimated_cost_usd),
    }


def _preview_task(
    template: str,
    task_name: str,
    profile: str,
    partition: str,
) -> TemplateJobPreview:
    backend = _template_backend(template)
    command = _template_command(template, task_name, profile, partition)
    estimated_cost = Decimal("0") if backend == "cloud" else Decimal("0")
    return TemplateJobPreview(task_name, profile, backend, command, estimated_cost)


def _template_backend(template: str) -> str:
    if template.startswith("cloud_"):
        return "cloud"
    if template in ("mx350_micro_gpu_test", "rtx4060ti_advanced_local"):
        return "gpu"
    return "cpu"


def _template_command(
    template: str,
    task_name: str,
    profile: str,
    partition: str,
) -> str:
    output_dir = _dashboard_job_dir() / task_name
    if template == "rtx4060ti_advanced_local":
        return _rtx_command(task_name, output_dir)
    if template.startswith("cloud_"):
        return _cloud_command(task_name, profile, partition, output_dir)
    if template == "mx350_micro_gpu_test":
        return _mx350_command(output_dir)
    return _local_simple_command(profile, output_dir)


def _local_simple_command(profile: str, output_dir: Path) -> str:
    return f"python manage.py run_local_simple_pipeline --profile {profile} --output-dir {output_dir}"


def _mx350_command(output_dir: Path) -> str:
    return (
        "python manage.py run_local_simple_pipeline --profile local_mx350_queue "
        f"--enable-micro-gpu --max-vram-gb 1.5 --queue --output-dir {output_dir}"
    )


def _rtx_command(task_name: str, output_dir: Path) -> str:
    return (
        "python manage.py run_analytics_pipeline --profile local_rtx4060ti "
        f"--backend gpu --task {task_name} --output-dir {output_dir}"
    )


def _cloud_command(
    task_name: str,
    profile: str,
    partition: str,
    output_dir: Path,
) -> str:
    return (
        f"python manage.py run_analytics_pipeline --profile {profile} "
        f"--backend cloud --task {task_name} --partition {partition} "
        f"--output-dir {output_dir}"
    )


def _template_tasks(template: str) -> tuple[str, ...]:
    try:
        return TEMPLATE_TASKS[template]
    except KeyError as error:
        expected = ", ".join(sorted(TEMPLATE_TASKS))
        raise ValueError(f"Invalid template {template!r}; expected one of: {expected}") from error


def _template_result(
    template: str,
    previews: tuple[TemplateJobPreview, ...],
    jobs: tuple[PipelineJob, ...],
) -> dict[str, object]:
    return {
        "template": template,
        "dry_run": not jobs,
        "preview": [_preview_payload(preview) for preview in previews],
        "job_ids": [job.pk for job in jobs],
    }


def _preview_payload(preview: TemplateJobPreview) -> dict[str, object]:
    return {
        "task_name": preview.task_name,
        "profile": preview.profile,
        "backend": preview.backend,
        "command": preview.command,
        "estimated_cost_usd": str(preview.estimated_cost_usd),
    }


def _dashboard_job_dir() -> Path:
    export_dir = getattr(settings, "PARQUET_EXPORT_DIR", Path("exports"))
    return Path(export_dir) / "dashboard_jobs"


TEMPLATE_TASKS: dict[str, tuple[str, ...]] = {
    "local_simple_pipeline": (
        "export_parquet",
        "build_asset_panel",
        "build_feature_store_basic",
        "build_mfdfa_small",
        "build_signature_simple",
        "build_graph_light",
        "build_model_dataset_basic",
    ),
    "mx350_micro_gpu_test": (
        "gpu_smoke_test",
        "wavelet_micro_batch",
        "mfdfa_micro_batch",
        "signature_micro_batch",
    ),
    "rtx4060ti_advanced_local": (
        "wavelet_gpu",
        "mfdfa_gpu_batched",
        "signature_gpu_batched",
        "graph_gpu_correlation",
        "tensor_export_pt",
    ),
    "cloud_student_advanced_plan": (
        "advanced_dtcwt",
        "large_mfdfa_batched",
        "large_graph_embedding",
        "mamba_experiment",
        "nrde_experiment",
        "glc_gnn_experiment",
    ),
    "cloud_backfill_partitioned": (
        "advanced_dtcwt",
        "large_mfdfa_batched",
        "large_graph_embedding",
        "tensor_export_large",
    ),
}
