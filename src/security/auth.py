"""API authentication and endpoint access policy."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import RuntimeSettings
from src.security.api_keys import api_key_matches, extract_api_key, hash_api_key

READ_METHODS = {"GET", "HEAD", "OPTIONS"}
HEAVY_ENDPOINT_PREFIXES = (
    "/ingest/run",
    "/features/build",
    "/models/train",
    "/model/train",
    "/train/run",
    "/backtest/run",
    "/risk/run",
    "/compute/runpod/submit",
    "/compute/runpod/cancel",
)


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Authentication decision for one request."""

    allowed: bool
    status_code: int
    principal: str = "anonymous"
    reason: str = "ok"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly decision."""
        return {
            "allowed": self.allowed,
            "status_code": self.status_code,
            "principal": self.principal,
            "reason": self.reason,
        }


def endpoint_requires_auth(path: str, method: str, settings: RuntimeSettings) -> bool:
    """Return whether an endpoint requires API key auth."""
    if not settings.security.api_auth_enabled:
        return False
    normalized_method = method.upper()
    normalized_path = _normalize_path(path)
    if normalized_method in READ_METHODS:
        return settings.security.read_only_requires_auth
    if normalized_method not in READ_METHODS:
        return True
    return any(normalized_path.startswith(prefix) for prefix in HEAVY_ENDPOINT_PREFIXES)


def authenticate_request(
    path: str,
    method: str,
    settings: RuntimeSettings,
    *,
    api_key_header: str | None = None,
    authorization_header: str | None = None,
) -> AuthResult:
    """Authenticate an endpoint request using configured API key hashes."""
    if not endpoint_requires_auth(path, method, settings):
        return AuthResult(True, 200)
    api_key = extract_api_key(api_key_header) or extract_api_key(authorization_header)
    if not api_key:
        return AuthResult(False, 401, reason="missing API key")
    if not settings.security.api_key_hashes:
        return AuthResult(False, 401, reason="no API keys configured")
    if not api_key_matches(api_key, settings.security.api_key_hashes):
        return AuthResult(False, 401, reason="invalid API key")
    return AuthResult(True, 200, principal=f"api_key:{hash_api_key(api_key)[:16]}")


def _normalize_path(path: str) -> str:
    value = path.strip() or "/"
    if not value.startswith("/"):
        value = "/" + value
    return value.rstrip("/") or "/"
