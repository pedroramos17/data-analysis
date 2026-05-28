"""Capture compute resource snapshots for the dashboard."""

import socket

from monitoring.compute.capabilities import detect_compute_capabilities
from monitoring.compute.native import detect_native_status
from monitoring.dashboard_models import ComputeProfileConfig, ComputeResourceSnapshot
from monitoring.orchestration.profile_config import sync_default_profile_configs


def capture_resource_snapshot(profile_name: str = "") -> ComputeResourceSnapshot:
    """Detect local resources and persist a dashboard snapshot.

    Example:
        `capture_resource_snapshot("local_cpu_low")`
    """
    sync_default_profile_configs()
    capabilities = detect_compute_capabilities()
    native_status = detect_native_status()
    profile = _profile_or_none(profile_name)
    return ComputeResourceSnapshot.objects.create(
        profile=profile,
        hostname=socket.gethostname(),
        cpu_count=capabilities.cpu_count,
        ram_total_gb=capabilities.ram_gb,
        ram_available_gb=capabilities.ram_gb,
        gpu_available=capabilities.cuda_available,
        gpu_name=capabilities.cuda_device_name,
        gpu_count=1 if capabilities.cuda_available else 0,
        gpu_total_vram_gb=capabilities.total_vram_gb,
        gpu_free_vram_gb=capabilities.total_vram_gb,
        torch_available=capabilities.torch_available,
        cuda_available=capabilities.cuda_available,
        cupy_available=capabilities.cupy_available,
        native_ctypes_available=native_status.available,
    )


def _profile_or_none(profile_name: str) -> ComputeProfileConfig | None:
    if not profile_name:
        return None
    return ComputeProfileConfig.objects.filter(profile_type=profile_name).first()
