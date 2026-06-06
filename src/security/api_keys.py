"""API key hashing and verification helpers."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable


def hash_api_key(api_key: str) -> str:
    """Return the SHA-256 hash used for API key comparison."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def api_key_matches(api_key: str, configured_hashes: Iterable[str]) -> bool:
    """Return whether an API key matches any configured hash."""
    candidate = hash_api_key(api_key)
    return any(hmac.compare_digest(candidate, configured.strip()) for configured in configured_hashes if configured.strip())


def extract_api_key(header_value: str | None) -> str:
    """Extract a raw API key from `X-API-Key` or `Authorization: Bearer` values."""
    if not header_value:
        return ""
    value = header_value.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value
