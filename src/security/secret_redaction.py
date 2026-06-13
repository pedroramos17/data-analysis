"""Shared secret redaction for logs, reports, and metadata."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
    "access_key",
)
SAFE_KEY_NAMES = {
    "api_token_logged",
    "api_key_count",
    "redact_secrets",
    "requires_short_lived_storage_credentials",
    "storage_credentials_scope",
}
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|credential|authorization|access[_-]?key)(\s*[=:]\s*)([^\s,;\]}]+)"
)
BEARER_PATTERN = re.compile(r"(?i)bearer\s+[a-z0-9._\-+/=]+")
QUERY_SECRET_PATTERN = re.compile(r"(?i)([?&](?:token|signature|x-amz-signature|api_key|apikey|secret)=)([^&\s]+)")


def redact_secrets(value: object, secret_values: Iterable[str] = ()) -> Any:
    """Recursively redact secret-looking keys and values."""
    secrets = tuple(item for item in secret_values if item)
    if isinstance(value, Mapping):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            redacted[key_text] = REDACTED if is_sensitive_key(key_text) else redact_secrets(item, secrets)
        return redacted
    if isinstance(value, list | tuple):
        return [redact_secrets(item, secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value


def redact_text(value: str, secret_values: Iterable[str] = ()) -> str:
    """Redact secret-looking text, tokens, and configured secret values."""
    redacted = value
    for secret in secret_values:
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    redacted = BEARER_PATTERN.sub("Bearer " + REDACTED, redacted)
    redacted = ASSIGNMENT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", redacted)
    redacted = QUERY_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{REDACTED}", redacted)
    return redacted


def is_sensitive_key(key: str) -> bool:
    """Return whether a mapping key should be redacted."""
    normalized = key.lower().replace("-", "_")
    if normalized in SAFE_KEY_NAMES:
        return False
    if normalized in SENSITIVE_KEY_PARTS:
        return True
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def env_secret_values(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return non-empty known secret values from environment-like input."""
    source = os.environ if env is None else env
    keys = (
        "RUNPOD_API_KEY",
        "API_KEYS",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "DATABASE_URL",
        "DJANGO_SECRET_KEY",
    )
    values: list[str] = []
    for key in keys:
        value = source.get(key, "")
        if key == "API_KEYS":
            values.extend(item.strip() for item in value.split(",") if item.strip())
        elif value:
            values.append(value)
    return tuple(dict.fromkeys(values))
