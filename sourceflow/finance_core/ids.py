"""Stable identifier helpers for finance artifacts."""

from __future__ import annotations

from hashlib import sha256


def stable_id(*parts: object, prefix: str = "fin") -> str:
    """Build a stable short identifier from ordered content parts."""

    payload = "\x1f".join(str(part) for part in parts)
    digest = sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
