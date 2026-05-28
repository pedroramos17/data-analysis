"""Task permission checks and backend routing."""

from monitoring.compute.backends import SelectedBackend, normalize_backend_name
from monitoring.compute.capabilities import (
    ComputeCapabilities,
    detect_compute_capabilities,
)
from monitoring.compute.profiles import ComputeProfile, get_compute_profile


def validate_task_allowed(task_name: str, profile: str) -> None:
    """Raise when a task is denied or absent from a profile policy.

    Example:
        `validate_task_allowed("ingestion", "local_cpu_low")`
    """
    compute_profile = get_compute_profile(profile)
    if task_name in compute_profile.denied_tasks:
        message = (
            f"Task {task_name!r} denied for profile {profile!r}; "
            "expected allowed task"
        )
        raise ValueError(message)
    if task_name not in compute_profile.allowed_tasks:
        expected = ", ".join(compute_profile.allowed_tasks)
        message = (
            f"Invalid task {task_name!r} for profile {profile!r}; "
            f"expected one of: {expected}"
        )
        raise ValueError(message)


def select_backend(
    task_name: str,
    requested_backend: str = "auto",
    profile: str = "local_cpu_low",
    capabilities: ComputeCapabilities | None = None,
) -> SelectedBackend:
    """Resolve the backend for a task with CPU fallback when allowed.

    Example:
        `select_backend("ingestion", profile="local_cpu_low")`
    """
    validate_task_allowed(task_name, profile)
    compute_profile = get_compute_profile(profile)
    detected = capabilities or detect_compute_capabilities()
    backend_name = normalize_backend_name(requested_backend)
    if backend_name == "auto":
        return _select_auto_backend(compute_profile, requested_backend, detected)
    return _select_requested_backend(
        compute_profile, backend_name, requested_backend, detected
    )


def _select_auto_backend(
    profile: ComputeProfile,
    requested_backend: str,
    capabilities: ComputeCapabilities,
) -> SelectedBackend:
    if profile.backend_preference == "cloud_manifest":
        return _cloud_backend(
            profile, requested_backend, "cloud profile routes to manifest"
        )
    if profile.allow_gpu and capabilities.cuda_available:
        return _cuda_backend(
            profile, requested_backend, capabilities, False, "GPU available"
        )
    if profile.allow_cpu:
        return _cpu_backend(
            profile, requested_backend, True, "GPU unavailable; using CPU"
        )
    return _cloud_backend(
        profile, requested_backend, "CPU unavailable; using cloud manifest"
    )


def _select_requested_backend(
    profile: ComputeProfile,
    backend_name: str,
    requested_backend: str,
    capabilities: ComputeCapabilities,
) -> SelectedBackend:
    if backend_name == "cpu":
        return _requested_cpu_backend(profile, requested_backend)
    if backend_name == "cloud_manifest":
        return _requested_cloud_backend(profile, requested_backend)
    if backend_name == "native":
        return _requested_native_backend(profile, requested_backend, capabilities)
    return _requested_gpu_backend(
        profile, backend_name, requested_backend, capabilities
    )


def _requested_cpu_backend(
    profile: ComputeProfile, requested_backend: str
) -> SelectedBackend:
    if not profile.allow_cpu:
        message = (
            f"Backend {requested_backend!r} invalid for profile {profile.name!r}; "
            "expected cloud"
        )
        raise ValueError(message)
    return _cpu_backend(profile, requested_backend, False, "CPU requested")


def _requested_cloud_backend(
    profile: ComputeProfile, requested_backend: str
) -> SelectedBackend:
    if not profile.allow_cloud:
        message = (
            f"Backend {requested_backend!r} invalid for profile {profile.name!r}; "
            "expected local backend"
        )
        raise ValueError(message)
    return _cloud_backend(profile, requested_backend, "cloud manifest requested")


def _requested_native_backend(
    profile: ComputeProfile,
    requested_backend: str,
    capabilities: ComputeCapabilities,
) -> SelectedBackend:
    if profile.allow_ctypes and capabilities.c_compiler_available:
        return SelectedBackend(
            "native", requested_backend, profile.name, "", False, "native requested"
        )
    if profile.allow_cpu:
        return _cpu_backend(
            profile, requested_backend, True, "native unavailable; using CPU"
        )
    message = (
        f"Backend {requested_backend!r} invalid for profile {profile.name!r}; "
        "expected CPU fallback"
    )
    raise ValueError(message)


def _requested_gpu_backend(
    profile: ComputeProfile,
    backend_name: str,
    requested_backend: str,
    capabilities: ComputeCapabilities,
) -> SelectedBackend:
    if not profile.allow_gpu:
        return _gpu_fallback_or_error(profile, requested_backend)
    if _gpu_backend_available(backend_name, capabilities):
        reason = f"{backend_name} requested and available"
        return _cuda_backend(profile, requested_backend, capabilities, False, reason)
    return _gpu_fallback_or_error(profile, requested_backend)


def _gpu_fallback_or_error(
    profile: ComputeProfile, requested_backend: str
) -> SelectedBackend:
    if profile.allow_cpu:
        return _cpu_backend(
            profile, requested_backend, True, "GPU unavailable; using CPU"
        )
    message = (
        f"Backend {requested_backend!r} invalid for profile {profile.name!r}; "
        "expected GPU"
    )
    raise ValueError(message)


def _gpu_backend_available(
    backend_name: str, capabilities: ComputeCapabilities
) -> bool:
    if backend_name == "cupy":
        return capabilities.cupy_available and capabilities.cuda_available
    return capabilities.cuda_available


def _cuda_backend(
    profile: ComputeProfile,
    requested_backend: str,
    capabilities: ComputeCapabilities,
    used_fallback: bool,
    reason: str,
) -> SelectedBackend:
    device = capabilities.cuda_device_name or "cuda:0"
    return SelectedBackend(
        "cuda", requested_backend, profile.name, device, used_fallback, reason
    )


def _cpu_backend(
    profile: ComputeProfile,
    requested_backend: str,
    used_fallback: bool,
    reason: str,
) -> SelectedBackend:
    return SelectedBackend(
        "cpu", requested_backend, profile.name, "cpu", used_fallback, reason
    )


def _cloud_backend(
    profile: ComputeProfile, requested_backend: str, reason: str
) -> SelectedBackend:
    return SelectedBackend(
        "cloud_manifest", requested_backend, profile.name, "cloud", False, reason
    )
