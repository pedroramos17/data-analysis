"""Execution profiles for local, GPU, and cloud-safe workloads."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComputeProfile:
    """Resource and task policy for one execution environment.

    Example:
        `profile = get_compute_profile("local_cpu_low")`
    """

    name: str
    description: str
    backend_preference: str
    allow_cpu: bool
    allow_gpu: bool
    allow_cloud: bool
    allow_ctypes: bool
    max_vram_gb: float
    max_ram_gb: float | None
    default_batch_size: int
    max_batch_size: int
    default_window: int
    max_window: int
    default_precision: str
    allowed_tasks: tuple[str, ...]
    denied_tasks: tuple[str, ...]
    queue_enabled: bool
    max_runtime_hours: float
    budget_guard_enabled: bool
    notes: tuple[str, ...]


LOCAL_CPU_ALLOWED_TASKS = (
    "ingestion",
    "export_parquet",
    "build_asset_panel",
    "build_feature_store_basic",
    "wavelet_basic",
    "build_mfdfa_small",
    "mfdfa_small",
    "build_signature_simple",
    "signature_simple",
    "build_graph_light",
    "graph_light",
    "build_model_dataset_basic",
)
LOCAL_CPU_DENIED_TASKS = (
    "train_mamba",
    "train_nrde",
    "train_glc_gnn",
    "wavelet_gpu",
    "mfdfa_gpu_batched",
    "signature_gpu_batched",
    "graph_gpu_correlation",
    "large_graph_embedding",
    "large_mfdfa_batched",
    "tensor_export_large",
)
MX350_ALLOWED_TASKS = (
    "gpu_smoke_test",
    "wavelet_micro_batch",
    "mfdfa_micro_batch",
    "signature_micro_batch",
    "small_tensor_export",
    "build_feature_store_basic",
    "wavelet_basic",
    "mfdfa_small",
    "signature_simple",
    "graph_light",
    "build_model_dataset_basic",
)
MX350_DENIED_TASKS = (
    "large_training",
    "large_correlation_graph",
    "full_history_gpu_pipeline",
    "train_mamba",
    "train_nrde",
    "train_glc_gnn",
    "large_graph_embedding",
    "tensor_export_large",
)
RTX_ALLOWED_TASKS = (
    "ingestion",
    "export_parquet",
    "build_asset_panel",
    "build_feature_store_basic",
    "wavelet_basic",
    "wavelet_gpu",
    "mfdfa_small",
    "mfdfa_gpu_batched",
    "signature_simple",
    "signature_gpu_batched",
    "graph_light",
    "graph_gpu_correlation",
    "large_graph_embedding",
    "build_model_dataset_basic",
    "tensor_export_pt",
    "tensor_export_large",
    "local_model_smoke_train",
)
CLOUD_STUDENT_ALLOWED_TASKS = (
    "advanced_dtcwt",
    "wavelet_gpu",
    "mfdfa_gpu_batched",
    "large_mfdfa_batched",
    "signature_gpu_batched",
    "graph_gpu_correlation",
    "large_graph_embedding",
    "graph_embedding",
    "tensor_export_large",
    "mamba_experiments",
    "mamba_experiment",
    "nrde_experiments",
    "nrde_experiment",
    "glc_gnn_experiments",
    "glc_gnn_experiment",
    "hyperparameter_sweep_small",
    "backfill_features",
)
CLOUD_STUDENT_DENIED_TASKS = (
    "unbounded_jobs",
    "jobs_without_budget",
    "jobs_without_manifest",
)
SERVERLESS_ALLOWED_TASKS = (
    "partitioned_backfills",
    "large_batch_feature_generation",
    "cloud_training",
    "scheduled_experiments",
    "advanced_dtcwt",
    "large_mfdfa_batched",
    "large_graph_embedding",
    "tensor_export_large",
)


COMPUTE_PROFILES: dict[str, ComputeProfile] = {
    "local_cpu_low": ComputeProfile(
        name="local_cpu_low",
        description="CPU-first notebook-safe profile for simple local work.",
        backend_preference="cpu",
        allow_cpu=True,
        allow_gpu=False,
        allow_cloud=False,
        allow_ctypes=True,
        max_vram_gb=0.0,
        max_ram_gb=4.0,
        default_batch_size=64,
        max_batch_size=256,
        default_window=128,
        max_window=512,
        default_precision="float32",
        allowed_tasks=LOCAL_CPU_ALLOWED_TASKS,
        denied_tasks=LOCAL_CPU_DENIED_TASKS,
        queue_enabled=False,
        max_runtime_hours=2.0,
        budget_guard_enabled=False,
        notes=("Safe default for ingestion, exports, and small features.",),
    ),
    "local_mx350_queue": ComputeProfile(
        name="local_mx350_queue",
        description="Low-end MX350 profile for slow local micro-batch queues.",
        backend_preference="cuda",
        allow_cpu=True,
        allow_gpu=True,
        allow_cloud=False,
        allow_ctypes=True,
        max_vram_gb=1.5,
        max_ram_gb=8.0,
        default_batch_size=8,
        max_batch_size=32,
        default_window=64,
        max_window=256,
        default_precision="float32",
        allowed_tasks=MX350_ALLOWED_TASKS,
        denied_tasks=MX350_DENIED_TASKS,
        queue_enabled=True,
        max_runtime_hours=72.0,
        budget_guard_enabled=False,
        notes=("Use only smoke tests, small windows, and CPU fallback.",),
    ),
    "local_rtx4060ti": ComputeProfile(
        name="local_rtx4060ti",
        description="GPU-first local profile for RTX 4060 Ti 16 GB systems.",
        backend_preference="cuda",
        allow_cpu=True,
        allow_gpu=True,
        allow_cloud=False,
        allow_ctypes=True,
        max_vram_gb=14.0,
        max_ram_gb=64.0,
        default_batch_size=512,
        max_batch_size=2048,
        default_window=512,
        max_window=4096,
        default_precision="float32",
        allowed_tasks=RTX_ALLOWED_TASKS,
        denied_tasks=(),
        queue_enabled=False,
        max_runtime_hours=24.0,
        budget_guard_enabled=False,
        notes=("Use local GPU acceleration with CPU fallback.",),
    ),
    "cloud_student": ComputeProfile(
        name="cloud_student",
        description="Cloud-first profile for partitioned student-credit jobs.",
        backend_preference="cloud_manifest",
        allow_cpu=True,
        allow_gpu=True,
        allow_cloud=True,
        allow_ctypes=False,
        max_vram_gb=8.0,
        max_ram_gb=16.0,
        default_batch_size=256,
        max_batch_size=1024,
        default_window=512,
        max_window=2048,
        default_precision="float32",
        allowed_tasks=CLOUD_STUDENT_ALLOWED_TASKS,
        denied_tasks=CLOUD_STUDENT_DENIED_TASKS,
        queue_enabled=True,
        max_runtime_hours=4.0,
        budget_guard_enabled=True,
        notes=("Generate manifests and keep provider choices portable.",),
    ),
    "cloud_serverless_on_demand": ComputeProfile(
        name="cloud_serverless_on_demand",
        description="Serverless/on-demand profile for idempotent backfills.",
        backend_preference="cloud_manifest",
        allow_cpu=True,
        allow_gpu=True,
        allow_cloud=True,
        allow_ctypes=False,
        max_vram_gb=24.0,
        max_ram_gb=64.0,
        default_batch_size=1024,
        max_batch_size=8192,
        default_window=1024,
        max_window=8192,
        default_precision="float32",
        allowed_tasks=SERVERLESS_ALLOWED_TASKS,
        denied_tasks=(),
        queue_enabled=True,
        max_runtime_hours=12.0,
        budget_guard_enabled=True,
        notes=("Prefer partitioned, restartable, portable job artifacts.",),
    ),
}


def get_compute_profile(name: str) -> ComputeProfile:
    """Return a named compute profile.

    Example:
        `get_compute_profile("local_cpu_low")`
    """
    database_profile = _database_compute_profile(name)
    if database_profile is not None:
        return database_profile
    try:
        return COMPUTE_PROFILES[name]
    except KeyError as error:
        expected = ", ".join(sorted(_profile_names()))
        message = f"Invalid profile {name!r}; expected one of: {expected}"
        raise ValueError(message) from error


def list_compute_profiles() -> tuple[ComputeProfile, ...]:
    """Return all registered compute profiles in stable order.

    Example:
        `profiles = list_compute_profiles()`
    """
    profiles = {name: profile for name, profile in COMPUTE_PROFILES.items()}
    profiles.update(_database_compute_profiles())
    return tuple(profiles[name] for name in sorted(profiles))


def compute_profile_from_setting(setting: object) -> ComputeProfile:
    """Build a runtime profile from a DB profile type setting.

    Example:
        `profile = compute_profile_from_setting(setting)`
    """
    return ComputeProfile(
        **_setting_identity(setting),
        **_setting_resources(setting),
        **_setting_task_policy(setting),
    )


def _setting_identity(setting: object) -> dict[str, object]:
    return {
        "name": str(getattr(setting, "slug")),
        "description": str(getattr(setting, "description", "")),
        "backend_preference": str(getattr(setting, "backend_preference", "auto")),
        "default_precision": str(getattr(setting, "default_precision", "float32")),
    }


def _setting_resources(setting: object) -> dict[str, object]:
    return {
        "allow_cpu": bool(getattr(setting, "allow_cpu", True)),
        "allow_gpu": bool(getattr(setting, "allow_gpu", False)),
        "allow_cloud": bool(getattr(setting, "allow_cloud", False)),
        "allow_ctypes": bool(getattr(setting, "allow_ctypes", True)),
        "max_vram_gb": float(getattr(setting, "max_vram_gb", 0.0)),
        "max_ram_gb": _optional_float(getattr(setting, "max_ram_gb", None)),
        "default_batch_size": int(getattr(setting, "default_batch_size", 64)),
        "max_batch_size": int(getattr(setting, "max_batch_size", 256)),
        "default_window": int(getattr(setting, "default_window", 128)),
        "max_window": int(getattr(setting, "max_window", 512)),
    }


def _setting_task_policy(setting: object) -> dict[str, object]:
    return {
        "allowed_tasks": _string_tuple(getattr(setting, "allowed_tasks_json", [])),
        "denied_tasks": _string_tuple(getattr(setting, "denied_tasks_json", [])),
        "queue_enabled": bool(getattr(setting, "queue_enabled", True)),
        "max_runtime_hours": float(getattr(setting, "max_runtime_hours", 2.0)),
        "budget_guard_enabled": bool(getattr(setting, "budget_guard_enabled", False)),
        "notes": _string_tuple(getattr(setting, "notes_json", [])),
    }


def _database_compute_profile(name: str) -> ComputeProfile | None:
    try:
        from monitoring.dashboard_models import ComputeProfileTypeSetting

        setting = ComputeProfileTypeSetting.objects.get(slug=name, enabled=True)
    except Exception:
        return None
    return compute_profile_from_setting(setting)


def _database_compute_profiles() -> dict[str, ComputeProfile]:
    try:
        from monitoring.dashboard_models import ComputeProfileTypeSetting

        rows = ComputeProfileTypeSetting.objects.filter(enabled=True)
    except Exception:
        return {}
    return {row.slug: compute_profile_from_setting(row) for row in rows}


def _profile_names() -> tuple[str, ...]:
    names = set(COMPUTE_PROFILES)
    names.update(_database_compute_profiles())
    return tuple(sorted(names))


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, Sequence):
        return ()
    return tuple(str(item) for item in value if str(item))


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
