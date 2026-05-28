"""Task registry for local/cloud analytics planning."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalyticsTask:
    """Planning metadata for one analytics task.

    Example:
        `task = get_analytics_task("mfdfa_small")`
    """

    name: str
    complexity: str
    local_allowed_profiles: tuple[str, ...]
    cloud_recommended: bool
    estimated_memory_formula: str
    estimated_vram_formula: str
    default_partition_strategy: str
    output_artifact_type: str


LOCAL_CPU = ("local_cpu_low", "local_mx350_queue", "local_rtx4060ti")
RTX_ONLY = ("local_rtx4060ti",)
CLOUD_PROFILES = ("cloud_student", "cloud_serverless_on_demand")


def _task(
    name: str,
    complexity: str,
    local_profiles: tuple[str, ...],
    cloud_recommended: bool,
    memory_formula: str,
    vram_formula: str,
) -> AnalyticsTask:
    return AnalyticsTask(
        name=name,
        complexity=complexity,
        local_allowed_profiles=local_profiles,
        cloud_recommended=cloud_recommended,
        estimated_memory_formula=memory_formula,
        estimated_vram_formula=vram_formula,
        default_partition_strategy="monthly",
        output_artifact_type=_artifact_type(name),
    )


def _artifact_type(task_name: str) -> str:
    if "graph" in task_name:
        return "graph_features"
    if "mamba" in task_name or "nrde" in task_name or "gnn" in task_name:
        return "experiment_metrics"
    if "tensor" in task_name or "dataset" in task_name:
        return "model_dataset"
    return "feature_table"


TASK_REGISTRY: dict[str, AnalyticsTask] = {
    "ingestion": _task(
        "ingestion", "simple", LOCAL_CPU, False, "sqlite+raw rows", "0"
    ),
    "export_parquet": _task(
        "export_parquet", "simple", LOCAL_CPU, False, "rows*cols", "0"
    ),
    "build_asset_panel": _task(
        "build_asset_panel", "simple", LOCAL_CPU, False, "rows*assets", "0"
    ),
    "build_feature_store_basic": _task(
        "build_feature_store_basic", "simple", LOCAL_CPU, False, "rows*features", "0"
    ),
    "wavelet_basic": _task(
        "wavelet_basic", "moderate", LOCAL_CPU, False, "rows*window", "0"
    ),
    "wavelet_gpu": _task(
        "wavelet_gpu", "heavy", RTX_ONLY, True, "rows*window", "batch*window"
    ),
    "advanced_dtcwt": _task(
        "advanced_dtcwt", "heavy", RTX_ONLY, True, "rows*window*scales",
        "batch*window*scales"
    ),
    "mfdfa_small": _task(
        "mfdfa_small", "moderate", LOCAL_CPU, False, "rows*scales", "0"
    ),
    "mfdfa_gpu_batched": _task(
        "mfdfa_gpu_batched", "heavy", RTX_ONLY, True, "rows*scales*q",
        "batch*scales*q"
    ),
    "large_mfdfa_batched": _task(
        "large_mfdfa_batched", "heavy", RTX_ONLY, True, "rows*scales*q",
        "batch*scales*q"
    ),
    "signature_simple": _task(
        "signature_simple", "moderate", LOCAL_CPU, False, "rows*channels^2", "0"
    ),
    "signature_gpu_batched": _task(
        "signature_gpu_batched", "heavy", RTX_ONLY, True, "batch*time*channels^2",
        "batch*time*channels^2"
    ),
    "graph_light": _task(
        "graph_light", "moderate", LOCAL_CPU, False, "features^2", "0"
    ),
    "graph_gpu_correlation": _task(
        "graph_gpu_correlation", "heavy", RTX_ONLY, True, "features^2",
        "features^2"
    ),
    "large_graph_embedding": _task(
        "large_graph_embedding", "heavy", RTX_ONLY, True, "nodes*edges",
        "nodes*edges"
    ),
    "graph_embedding": _task(
        "graph_embedding", "heavy", RTX_ONLY, True, "nodes*edges", "nodes*edges"
    ),
    "build_model_dataset_basic": _task(
        "build_model_dataset_basic", "moderate", LOCAL_CPU, False,
        "samples*window*features", "0"
    ),
    "tensor_export_large": _task(
        "tensor_export_large", "heavy", RTX_ONLY, True, "samples*window*features",
        "batch*window*features"
    ),
    "train_mamba": _task(
        "train_mamba", "experimental", (), True, "model*dataset",
        "model*batch*window"
    ),
    "mamba_experiment": _task(
        "mamba_experiment", "experimental", RTX_ONLY, True, "model*dataset",
        "model*batch*window"
    ),
    "train_nrde": _task(
        "train_nrde", "experimental", (), True, "model*dataset",
        "model*batch*window"
    ),
    "nrde_experiment": _task(
        "nrde_experiment", "experimental", RTX_ONLY, True, "model*dataset",
        "model*batch*window"
    ),
    "train_glc_gnn": _task(
        "train_glc_gnn", "experimental", (), True, "nodes*edges*layers",
        "nodes*edges*layers"
    ),
    "glc_gnn_experiment": _task(
        "glc_gnn_experiment", "experimental", RTX_ONLY, True,
        "nodes*edges*layers", "nodes*edges*layers"
    ),
}


DEFAULT_PIPELINE_TASKS = (
    "build_feature_store_basic",
    "wavelet_basic",
    "advanced_dtcwt",
    "mfdfa_small",
    "large_mfdfa_batched",
    "signature_simple",
    "signature_gpu_batched",
    "graph_light",
    "large_graph_embedding",
    "build_model_dataset_basic",
    "tensor_export_large",
    "mamba_experiment",
    "nrde_experiment",
    "glc_gnn_experiment",
)


ADVANCED_CLOUD_TASKS = (
    "advanced_dtcwt",
    "large_mfdfa_batched",
    "signature_gpu_batched",
    "large_graph_embedding",
    "tensor_export_large",
    "mamba_experiment",
    "nrde_experiment",
    "glc_gnn_experiment",
)


def get_analytics_task(name: str) -> AnalyticsTask:
    """Return planning metadata for one task.

    Example:
        `get_analytics_task("graph_light")`
    """
    try:
        return TASK_REGISTRY[name]
    except KeyError as error:
        expected = ", ".join(sorted(TASK_REGISTRY))
        message = f"Invalid task {name!r}; expected one of: {expected}"
        raise ValueError(message) from error


def list_analytics_tasks() -> tuple[AnalyticsTask, ...]:
    """Return all registered tasks in stable order.

    Example:
        `tasks = list_analytics_tasks()`
    """
    return tuple(TASK_REGISTRY[name] for name in sorted(TASK_REGISTRY))


def default_pipeline_tasks() -> tuple[str, ...]:
    """Return the default full planning task list.

    Example:
        `tasks = default_pipeline_tasks()`
    """
    return DEFAULT_PIPELINE_TASKS


def advanced_cloud_tasks() -> tuple[str, ...]:
    """Return advanced tasks that should be cloud-planned by default.

    Example:
        `tasks = advanced_cloud_tasks()`
    """
    return ADVANCED_CLOUD_TASKS
