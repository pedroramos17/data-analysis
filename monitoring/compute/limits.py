"""Resource limit application and coarse job size estimates."""

import math
from collections.abc import Mapping
from dataclasses import dataclass

from monitoring.compute.profiles import ComputeProfile, get_compute_profile


@dataclass(frozen=True, slots=True)
class JobSizeEstimate:
    """Coarse size estimate for routing and manifest planning.

    Example:
        `estimate = estimate_job_size(1000, 20, 64, 32, "local_cpu_low")`
    """

    rows: int
    columns: int
    window: int
    batch_size: int
    partition_count: int
    estimated_values: int
    estimated_bytes: int
    estimated_gb: float
    profile: str


def apply_resource_limits(
    task_config: Mapping[str, object], profile: str
) -> dict[str, object]:
    """Clamp task config to profile batch, window, memory, and guard limits.

    Example:
        `apply_resource_limits({"batch_size": 9999}, "local_cpu_low")`
    """
    compute_profile = get_compute_profile(profile)
    _validate_cloud_guard(task_config, compute_profile)
    limited_config = dict(task_config)
    limited_config["profile"] = compute_profile.name
    limited_config["batch_size"] = _limited_batch_size(task_config, compute_profile)
    limited_config["window"] = _limited_window(task_config, compute_profile)
    limited_config["precision"] = _precision(task_config, compute_profile)
    limited_config["max_vram_gb"] = _limited_vram_gb(task_config, compute_profile)
    limited_config["max_runtime_hours"] = compute_profile.max_runtime_hours
    limited_config["queue_enabled"] = compute_profile.queue_enabled
    limited_config["budget_guard_enabled"] = compute_profile.budget_guard_enabled
    return limited_config


def estimate_job_size(
    rows: int,
    columns: int,
    window: int,
    batch_size: int,
    profile: str,
) -> JobSizeEstimate:
    """Estimate values, bytes, and partitions for a bounded job.

    Example:
        `estimate_job_size(1000, 10, 64, 32, "local_cpu_low")`
    """
    compute_profile = get_compute_profile(profile)
    checked_rows = _positive_int(rows, "rows")
    checked_columns = _positive_int(columns, "columns")
    checked_window = min(_positive_int(window, "window"), compute_profile.max_window)
    checked_batch = min(
        _positive_int(batch_size, "batch_size"), compute_profile.max_batch_size
    )
    values = checked_rows * checked_columns * checked_window
    estimated_bytes = values * _bytes_per_value(compute_profile.default_precision)
    return JobSizeEstimate(
        checked_rows,
        checked_columns,
        checked_window,
        checked_batch,
        math.ceil(checked_rows / checked_batch),
        values,
        estimated_bytes,
        round(estimated_bytes / (1024**3), 6),
        compute_profile.name,
    )


def _validate_cloud_guard(
    task_config: Mapping[str, object], profile: ComputeProfile
) -> None:
    if not profile.budget_guard_enabled or task_config.get("execute") is not True:
        return
    if task_config.get("manifest_path") and task_config.get("max_cost_usd") is not None:
        return
    message = (
        f"Invalid cloud task config {dict(task_config)!r}; "
        "expected manifest_path and max_cost_usd before execution"
    )
    raise ValueError(message)


def _limited_batch_size(
    task_config: Mapping[str, object], profile: ComputeProfile
) -> int:
    value = task_config.get("batch_size", profile.default_batch_size)
    requested = _positive_int(value, "batch_size")
    return min(requested, profile.max_batch_size)


def _limited_window(task_config: Mapping[str, object], profile: ComputeProfile) -> int:
    value = task_config.get("window", profile.default_window)
    requested = _positive_int(value, "window")
    return min(requested, profile.max_window)


def _precision(task_config: Mapping[str, object], profile: ComputeProfile) -> str:
    value = str(task_config.get("precision", profile.default_precision))
    if value not in ("float16", "float32", "float64"):
        message = f"Invalid precision {value!r}; expected float16, float32, or float64"
        raise ValueError(message)
    return value


def _limited_vram_gb(
    task_config: Mapping[str, object], profile: ComputeProfile
) -> float:
    requested = _optional_float(task_config.get("max_vram_gb"))
    if requested is None:
        return profile.max_vram_gb
    return min(requested, profile.max_vram_gb)


def _positive_int(value: object, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        message = f"Invalid {field_name} {value!r}; expected positive integer"
        raise ValueError(message) from error
    if parsed <= 0:
        raise ValueError(f"Invalid {field_name} {value!r}; expected positive integer")
    return parsed


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid max_vram_gb {value!r}; expected number") from error


def _bytes_per_value(precision: str) -> int:
    if precision == "float16":
        return 2
    if precision == "float64":
        return 8
    return 4
