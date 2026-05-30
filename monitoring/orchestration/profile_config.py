"""Synchronize editable dashboard profile rows from compute profiles."""

from monitoring.compute.profiles import (
    COMPUTE_PROFILES,
    ComputeProfile,
    compute_profile_from_setting,
)
from monitoring.dashboard_models import ComputeProfileConfig, ComputeProfileTypeSetting


def sync_profile_type_settings() -> tuple[ComputeProfileTypeSetting, ...]:
    """Create missing profile type rows from built-in profile seeds.

    Example:
        `profile_types = sync_profile_type_settings()`
    """
    rows = []
    for compute_profile in COMPUTE_PROFILES.values():
        setting = _get_or_create_profile_type_setting(compute_profile)
        rows.append(setting)
    return tuple(rows)


def sync_default_profile_configs() -> tuple[ComputeProfileConfig, ...]:
    """Create missing dashboard profile config rows.

    Example:
        `profiles = sync_default_profile_configs()`
    """
    sync_profile_type_settings()
    created_profiles = []
    for setting in ComputeProfileTypeSetting.objects.filter(enabled=True):
        profile = compute_profile_from_setting(setting)
        config = _get_or_create_profile_config(profile)
        created_profiles.append(config)
    return tuple(created_profiles)


def _get_or_create_profile_type_setting(
    profile: ComputeProfile,
) -> ComputeProfileTypeSetting:
    setting, _created = ComputeProfileTypeSetting.objects.get_or_create(
        slug=profile.name,
        defaults=_profile_type_defaults(profile),
    )
    return setting


def _get_or_create_profile_config(profile: ComputeProfile) -> ComputeProfileConfig:
    config, _created = ComputeProfileConfig.objects.get_or_create(
        name=profile.name,
        defaults=_profile_config_defaults(profile),
    )
    return config


def _profile_type_defaults(profile: ComputeProfile) -> dict[str, object]:
    defaults = _profile_type_identity(profile)
    defaults.update(_profile_type_resources(profile))
    defaults.update(_profile_type_policy(profile))
    return defaults


def _profile_type_identity(profile: ComputeProfile) -> dict[str, object]:
    return {
        "label": _profile_label(profile.name),
        "enabled": True,
        "description": profile.description,
        "backend_preference": profile.backend_preference,
        "default_precision": profile.default_precision,
    }


def _profile_type_resources(profile: ComputeProfile) -> dict[str, object]:
    return {
        "allow_cpu": profile.allow_cpu,
        "allow_gpu": profile.allow_gpu,
        "allow_cloud": profile.allow_cloud,
        "allow_ctypes": profile.allow_ctypes,
        "max_vram_gb": profile.max_vram_gb,
        "max_ram_gb": profile.max_ram_gb,
        "default_batch_size": profile.default_batch_size,
        "max_batch_size": profile.max_batch_size,
        "default_window": profile.default_window,
        "max_window": profile.max_window,
    }


def _profile_type_policy(profile: ComputeProfile) -> dict[str, object]:
    return {
        "allowed_tasks_json": list(profile.allowed_tasks),
        "denied_tasks_json": list(profile.denied_tasks),
        "queue_enabled": profile.queue_enabled,
        "max_runtime_hours": profile.max_runtime_hours,
        "budget_guard_enabled": profile.budget_guard_enabled,
        "notes_json": list(profile.notes),
    }


def _profile_config_defaults(profile: ComputeProfile) -> dict[str, object]:
    return {
        "profile_type": profile.name,
        "enabled": True,
        "backend_preference": _backend_preference(profile.backend_preference),
        "max_cpu_workers": 1,
        "max_gpu_workers": 1 if profile.allow_gpu else 0,
        "max_vram_gb": profile.max_vram_gb,
        "max_ram_gb": profile.max_ram_gb or 0,
        "default_batch_size": profile.default_batch_size,
        "max_batch_size": profile.max_batch_size,
        "default_window": profile.default_window,
        "max_window": profile.max_window,
        "default_precision": profile.default_precision,
        "queue_enabled": True,
        "cloud_enabled": profile.allow_cloud,
        "notes": "\n".join(profile.notes),
    }


def _profile_label(slug: str) -> str:
    return slug.replace("_", " ").title()


def _backend_preference(value: str) -> str:
    if value in ("cuda", "cupy"):
        return "gpu"
    if value == "cloud_manifest":
        return "cloud"
    if value in ("cpu", "gpu", "cloud", "auto"):
        return value
    return "auto"
