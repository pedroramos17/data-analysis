"""Point-in-time leakage controls for finance datasets."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime


def assert_no_lookahead(rows: Iterable[Mapping[str, object]]) -> None:
    """Raise when a feature becomes available after its prediction timestamp.

    Example:
        `assert_no_lookahead(rows)`
    """
    for row in rows:
        _check_row(row)


def fundamental_available_at(row: Mapping[str, object]) -> datetime:
    """Return fundamental availability from filed_at, not fiscal period end.

    Example:
        `available_at = fundamental_available_at(fact_row)`
    """
    return _timestamp(row["filed_at"])


def macro_available_at(row: Mapping[str, object]) -> datetime:
    """Return macro availability from realtime vintage when present.

    Example:
        `available_at = macro_available_at(observation)`
    """
    value = row.get("realtime_start") or row.get("date")
    return _timestamp(value)


def market_feature_available_at(row: Mapping[str, object]) -> datetime:
    """Return market feature availability from the row timestamp.

    Example:
        `available_at = market_feature_available_at(row)`
    """
    return _timestamp(row["timestamp"])


def _check_row(row: Mapping[str, object]) -> None:
    timestamp = _timestamp(row["timestamp"])
    available_at = _timestamp(row["available_at"])
    if available_at <= timestamp:
        return
    feature = row.get("feature_name", "unknown")
    available_text = available_at.isoformat()
    timestamp_text = timestamp.isoformat()
    raise ValueError(
        f"Lookahead leak for feature {feature!r}: "
        f"available_at={available_text} after timestamp={timestamp_text}"
    )


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return _aware(value)
    text = str(value).replace("Z", "+00:00")
    return _aware(datetime.fromisoformat(text))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
