"""Append-only JSONL audit logging for sensitive operations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.config.settings import RuntimeSettings, load_runtime_settings
from src.security.secret_redaction import env_secret_values, redact_secrets


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One security audit event."""

    action: str
    principal: str = "unknown"
    status: str = "started"
    target: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly event."""
        return {
            "created_at": self.created_at,
            "action": self.action,
            "principal": self.principal,
            "status": self.status,
            "target": self.target,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AuditLogger:
    """Write redacted audit events to JSONL."""

    path: Path
    secret_values: tuple[str, ...] = ()

    @classmethod
    def from_settings(cls, settings: RuntimeSettings) -> AuditLogger:
        """Build an audit logger from runtime settings."""
        secrets = env_secret_values() + tuple(value for value in (settings.runpod.api_key,) if value)
        return cls(settings.security.audit_log_path, tuple(dict.fromkeys(secrets)))

    def write(self, event: AuditEvent | Mapping[str, object]) -> Path:
        """Append a redacted event and return the log path."""
        payload = event.to_dict() if isinstance(event, AuditEvent) else dict(event)
        redacted = redact_secrets(payload, self.secret_values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(redacted, sort_keys=True, default=str) + "\n")
        return self.path


def audit_gpu_submit(
    settings: RuntimeSettings,
    *,
    principal: str,
    status: str,
    metadata: Mapping[str, object],
) -> Path:
    """Record a GPU submit audit event."""
    return AuditLogger.from_settings(settings).write(
        AuditEvent("gpu.submit", principal=principal, status=status, target="runpod", metadata=metadata)
    )


def audit_gpu_cancel(
    settings: RuntimeSettings,
    *,
    principal: str,
    status: str,
    job_id: str,
    metadata: Mapping[str, object] | None = None,
) -> Path:
    """Record a GPU cancel audit event."""
    return AuditLogger.from_settings(settings).write(
        AuditEvent("gpu.cancel", principal=principal, status=status, target=job_id, metadata=metadata or {})
    )


def default_audit_logger() -> AuditLogger:
    """Return the default audit logger."""
    return AuditLogger.from_settings(load_runtime_settings())
