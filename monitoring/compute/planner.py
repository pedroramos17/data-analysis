"""Pipeline planner that separates local tasks from cloud manifests."""

from dataclasses import asdict, dataclass
from pathlib import Path
import json
from collections.abc import Mapping

from monitoring.compute.limits import apply_resource_limits, estimate_job_size
from monitoring.compute.profiles import get_compute_profile
from monitoring.compute.task_registry import (
    AnalyticsTask,
    default_pipeline_tasks,
    get_analytics_task,
)


@dataclass(frozen=True, slots=True)
class PlannedTask:
    """One task placement decision in an analytics plan.

    Example:
        `planned = PlannedTask(task, "local", "local_cpu_low", "cpu", {}, {})`
    """

    task: AnalyticsTask
    placement: str
    profile: str
    backend: str
    limits: Mapping[str, object]
    estimate: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    """Complete local/cloud split for requested analytics tasks.

    Example:
        `plan = plan_pipeline("local_cpu_low", (), {})`
    """

    profile: str
    advanced_target: str
    requested_tasks: tuple[str, ...]
    local_tasks: tuple[PlannedTask, ...]
    cloud_tasks: tuple[PlannedTask, ...]
    dataset_stats: Mapping[str, object]


def plan_pipeline(
    profile: str,
    requested_tasks: tuple[str, ...] | list[str] | None,
    dataset_stats: Mapping[str, object],
    advanced_target: str = "cloud_student",
) -> PipelinePlan:
    """Plan requested tasks across local and cloud placements.

    Example:
        `plan_pipeline("local_cpu_low", None, {"rows": 100})`
    """
    local_profile = get_compute_profile(profile)
    cloud_profile = get_compute_profile(advanced_target)
    task_names = tuple(requested_tasks or default_pipeline_tasks())
    planned = tuple(
        _plan_task(name, local_profile.name, cloud_profile.name, dataset_stats)
        for name in task_names
    )
    local_tasks, cloud_tasks = split_local_and_cloud_tasks(planned)
    return PipelinePlan(
        local_profile.name,
        cloud_profile.name,
        task_names,
        local_tasks,
        cloud_tasks,
        dict(dataset_stats),
    )


def split_local_and_cloud_tasks(
    planned_tasks: tuple[PlannedTask, ...] | list[PlannedTask],
) -> tuple[tuple[PlannedTask, ...], tuple[PlannedTask, ...]]:
    """Split planned tasks into local and cloud tuples.

    Example:
        `local, cloud = split_local_and_cloud_tasks(plan.local_tasks)`
    """
    local = tuple(task for task in planned_tasks if task.placement == "local")
    cloud = tuple(task for task in planned_tasks if task.placement == "cloud")
    return local, cloud


def render_plan_summary(plan: PipelinePlan) -> str:
    """Render a concise human-readable plan summary.

    Example:
        `summary = render_plan_summary(plan)`
    """
    local_names = ", ".join(task.task.name for task in plan.local_tasks) or "none"
    cloud_names = ", ".join(task.task.name for task in plan.cloud_tasks) or "none"
    return (
        f"profile={plan.profile}; advanced_target={plan.advanced_target}; "
        f"local={local_names}; cloud={cloud_names}"
    )


def write_plan_manifest(plan: PipelinePlan, output_path: Path) -> Path:
    """Write a pipeline plan JSON manifest.

    Example:
        `write_plan_manifest(plan, Path("exports/pipeline_plan.json"))`
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_plan_payload(plan), indent=2), encoding="utf-8")
    return output_path


def _plan_task(
    task_name: str,
    profile: str,
    advanced_target: str,
    dataset_stats: Mapping[str, object],
) -> PlannedTask:
    task = get_analytics_task(task_name)
    placement = _task_placement(task, profile)
    target_profile = profile if placement == "local" else advanced_target
    backend = _task_backend(task, placement, profile)
    limits = apply_resource_limits(_task_config(dataset_stats), target_profile)
    estimate = asdict(_task_estimate(dataset_stats, limits, target_profile))
    return PlannedTask(task, placement, target_profile, backend, limits, estimate)


def _task_placement(task: AnalyticsTask, profile: str) -> str:
    if profile in task.local_allowed_profiles and not task.cloud_recommended:
        return "local"
    if profile == "local_rtx4060ti" and profile in task.local_allowed_profiles:
        return "local"
    return "cloud"


def _task_backend(task: AnalyticsTask, placement: str, profile: str) -> str:
    if placement == "cloud":
        return "cloud_manifest"
    if profile == "local_cpu_low":
        return "cpu"
    if profile == "local_mx350_queue" and task.complexity != "simple":
        return "auto"
    return "auto"


def _task_config(dataset_stats: Mapping[str, object]) -> dict[str, object]:
    return {
        "batch_size": dataset_stats.get("batch_size", 64),
        "window": dataset_stats.get("window", 128),
        "precision": dataset_stats.get("precision", "float32"),
        "max_vram_gb": dataset_stats.get("max_vram_gb", ""),
    }


def _task_estimate(
    dataset_stats: Mapping[str, object],
    limits: Mapping[str, object],
    profile: str,
) -> object:
    rows = int(dataset_stats.get("rows", 1000))
    columns = int(dataset_stats.get("columns", 16))
    window = int(limits["window"])
    batch_size = int(limits["batch_size"])
    return estimate_job_size(rows, columns, window, batch_size, profile)


def _plan_payload(plan: PipelinePlan) -> dict[str, object]:
    return {
        "profile": plan.profile,
        "advanced_target": plan.advanced_target,
        "requested_tasks": list(plan.requested_tasks),
        "dataset_stats": dict(plan.dataset_stats),
        "summary": render_plan_summary(plan),
        "local_tasks": [_planned_task_payload(task) for task in plan.local_tasks],
        "cloud_tasks": [_planned_task_payload(task) for task in plan.cloud_tasks],
    }


def _planned_task_payload(planned_task: PlannedTask) -> dict[str, object]:
    payload = asdict(planned_task.task)
    payload.update(
        {
            "placement": planned_task.placement,
            "profile": planned_task.profile,
            "backend": planned_task.backend,
            "limits": dict(planned_task.limits),
            "estimate": dict(planned_task.estimate),
        }
    )
    return payload
