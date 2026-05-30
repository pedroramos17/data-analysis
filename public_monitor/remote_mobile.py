"""Development-only remote mobile testing settings."""

from __future__ import annotations

import os
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured

TRUE_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})


@dataclass(frozen=True, slots=True)
class RemoteMobileSettings:
    """Resolved development tunnel settings.

    Example:
        `settings = build_remote_mobile_settings(True, ["localhost"])`
    """

    enabled: bool
    public_base_url: str
    allowed_hosts: list[str]
    extra_allowed_hosts: list[str]
    csrf_trusted_origins: list[str]
    provider: str
    notes: str


def build_remote_mobile_settings(
    debug: bool,
    base_allowed_hosts: Sequence[str],
    environ: Mapping[str, str] | None = None,
) -> RemoteMobileSettings:
    """Return DEBUG-only public tunnel settings.

    Example:
        `result = build_remote_mobile_settings(DEBUG, ALLOWED_HOSTS)`
    """
    env = environ or os.environ
    _reject_production_wildcards(debug, base_allowed_hosts)
    if not debug or not _env_bool(env.get("ENABLE_REMOTE_MOBILE_TESTING")):
        return _disabled_settings(base_allowed_hosts)
    extra_hosts = _csv_values(env.get("DEV_EXTRA_ALLOWED_HOSTS"))
    csrf_origins = _csv_values(env.get("DEV_CSRF_TRUSTED_ORIGINS"))
    return RemoteMobileSettings(
        enabled=True,
        public_base_url=str(env.get("DEV_PUBLIC_BASE_URL", "")).strip(),
        allowed_hosts=_dedupe([*base_allowed_hosts, *extra_hosts]),
        extra_allowed_hosts=extra_hosts,
        csrf_trusted_origins=csrf_origins,
        provider=str(env.get("DEV_TUNNEL_PROVIDER", "")).strip(),
        notes=str(env.get("DEV_TUNNEL_NOTES", "")).strip(),
    )


def warn_remote_mobile_testing(settings: RemoteMobileSettings) -> None:
    """Emit a startup warning when public mobile testing is enabled.

    Example:
        `warn_remote_mobile_testing(remote_mobile_settings)`
    """
    if not settings.enabled:
        return
    warnings.warn(
        "Remote mobile testing is enabled for DEBUG only. Use a public HTTPS "
        "tunnel URL and do not expose admin publicly without authentication.",
        RuntimeWarning,
        stacklevel=2,
    )


def _disabled_settings(base_allowed_hosts: Sequence[str]) -> RemoteMobileSettings:
    return RemoteMobileSettings(
        enabled=False,
        public_base_url="",
        allowed_hosts=_dedupe(base_allowed_hosts),
        extra_allowed_hosts=[],
        csrf_trusted_origins=[],
        provider="",
        notes="",
    )


def _reject_production_wildcards(
    debug: bool,
    base_allowed_hosts: Sequence[str],
) -> None:
    if debug or "*" not in base_allowed_hosts:
        return
    raise ImproperlyConfigured(
        "Invalid ALLOWED_HOSTS contains '*' outside DEBUG; expected exact hosts"
    )


def _csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _env_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES
