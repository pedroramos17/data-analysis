"""Central feature flag lookup for Sourceflow finance modules."""

from __future__ import annotations

import os
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from sourceflow.config.default_flags import DEFAULT_FEATURE_FLAGS

TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
FALSE_VALUES = frozenset({"0", "false", "no", "off", "disabled"})


class FeatureDisabledError(RuntimeError):
    """Raised when a flagged Sourceflow feature is disabled.

    Example:
        `require_feature("FIN_MODEL_MCI_GRU")`
    """


@dataclass(frozen=True, slots=True)
class FeatureFlagState:
    """Resolved feature flag value and source metadata.

    Example:
        `state = resolve_feature_flag("FIN_DATA_CORE")`
    """

    name: str
    enabled: bool
    source: str


def feature_flag_enabled(name: str) -> bool:
    """Return whether a Sourceflow feature flag is enabled.

    Example:
        `if feature_flag_enabled("FIN_DATA_SEC_EDGAR"): ...`
    """
    return resolve_feature_flag(name).enabled


def require_feature(name: str) -> None:
    """Raise FeatureDisabledError when a feature flag is off.

    Example:
        `require_feature("FIN_MODEL_EXPERIMENTAL_TORCH")`
    """
    state = resolve_feature_flag(name)
    if state.enabled:
        return
    raise FeatureDisabledError(
        f"Feature flag {name} is disabled from {state.source}; expected true"
    )


def resolve_feature_flag(name: str) -> FeatureFlagState:
    """Resolve a flag from settings, environment, SQLite, or defaults.

    Example:
        `resolve_feature_flag("FIN_DATA_CORE").source`
    """
    _validate_flag_name(name)
    setting_value = _settings_override(name)
    if setting_value is not None:
        return FeatureFlagState(name, setting_value, "settings")
    env_value = _environment_override(name)
    if env_value is not None:
        return FeatureFlagState(name, env_value, "environment")
    sqlite_value = _sqlite_override(name)
    if sqlite_value is not None:
        return FeatureFlagState(name, sqlite_value, "sqlite")
    return FeatureFlagState(name, DEFAULT_FEATURE_FLAGS[name], "default")


def list_feature_flags() -> list[FeatureFlagState]:
    """Return all known feature flags with resolved states.

    Example:
        `states = list_feature_flags()`
    """
    return [resolve_feature_flag(name) for name in sorted(DEFAULT_FEATURE_FLAGS)]


def set_feature_flag(name: str, enabled: bool) -> FeatureFlagState:
    """Persist a flag override in SQLite-backed Django settings.

    Example:
        `set_feature_flag("FIN_MODEL_GNN", False)`
    """
    _validate_flag_name(name)
    model = _feature_flag_model()
    model.objects.update_or_create(name=name, defaults={"enabled": enabled})
    return FeatureFlagState(name=name, enabled=enabled, source="sqlite")


def parse_flag_value(value: object) -> bool:
    """Parse common CLI/env boolean flag values.

    Example:
        `parse_flag_value("true")`
    """
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"Invalid flag value {value!r}; expected true or false")


def _validate_flag_name(name: str) -> None:
    if name in DEFAULT_FEATURE_FLAGS:
        return
    flag_names = sorted(DEFAULT_FEATURE_FLAGS)
    raise ImproperlyConfigured(
        f"Unknown feature flag {name!r}; expected one of {flag_names}"
    )


def _settings_override(name: str) -> bool | None:
    if not settings.configured:
        return None
    overrides = getattr(settings, "SOURCEFLOW_FEATURE_FLAGS", {})
    if not isinstance(overrides, dict) or name not in overrides:
        return None
    return parse_flag_value(overrides[name])


def _environment_override(name: str) -> bool | None:
    raw_value = os.getenv(f"SOURCEFLOW_FLAG_{name}")
    if raw_value is None:
        return None
    return parse_flag_value(raw_value)


def _sqlite_override(name: str) -> bool | None:
    try:
        model = _feature_flag_model()
        row = model.objects.filter(name=name).only("enabled").first()
    except Exception:
        return None
    return None if row is None else bool(row.enabled)


def _feature_flag_model() -> type:
    from monitoring.models import FeatureFlagSetting

    return FeatureFlagSetting
