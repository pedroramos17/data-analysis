"""Time normalization helpers for point-in-time finance records."""

from __future__ import annotations

from datetime import datetime, timezone


def require_datetime(value: object, label: str = "timestamp") -> datetime:
    """Return a timezone-aware datetime or raise a clear contract error."""

    if not isinstance(value, datetime):
        raise ValueError(f"Invalid {label} {value!r}; expected datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
