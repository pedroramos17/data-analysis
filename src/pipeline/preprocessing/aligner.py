"""Deterministic row ordering and calendar alignment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta


def sort_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Sort rows by symbol, timeframe, timestamp, and source."""
    return [dict(row) for row in sorted(rows, key=_sort_key)]


def remove_duplicates(rows: Sequence[Mapping[str, object]]) -> tuple[list[dict[str, object]], int]:
    """Remove exact timestamp duplicates deterministically."""
    seen: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in sort_rows(rows):
        key = (
            str(row.get("symbol") or ""),
            str(row.get("timeframe") or ""),
            str(row.get("ts") or ""),
        )
        seen.setdefault(key, dict(row))
    deduped = sort_rows(seen.values())
    return deduped, max(len(rows) - len(deduped), 0)


def align_calendar(
    rows: Sequence[Mapping[str, object]],
    *,
    frequency: str = "1d",
    explicit_calendar: Sequence[str] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Align rows to an explicit calendar without looking ahead.

    Daily frequency inserts missing sessions between the observed min/max or the
    provided explicit calendar. Other frequencies are only sorted and reported.
    """
    if frequency != "1d":
        sorted_rows = sort_rows(rows)
        return sorted_rows, {"frequency": frequency, "inserted_rows": 0, "explicit": bool(explicit_calendar)}
    output: list[dict[str, object]] = []
    inserted = 0
    grouped = _group_symbol_timeframe(rows)
    for key in sorted(grouped):
        group = sort_rows(grouped[key])
        calendar = _calendar_for_group(group, explicit_calendar)
        rows_by_date = {_timestamp(row["ts"]).date().isoformat(): dict(row) for row in group}
        previous: dict[str, object] | None = None
        for day in calendar:
            existing = rows_by_date.get(day)
            if existing is not None:
                output.append(existing)
                previous = existing
                continue
            if previous is None:
                continue
            inserted_row = _missing_calendar_row(previous, day)
            output.append(inserted_row)
            previous = inserted_row
            inserted += 1
    return sort_rows(output), {"frequency": frequency, "inserted_rows": inserted, "explicit": bool(explicit_calendar)}


def _missing_calendar_row(previous: Mapping[str, object], day: str) -> dict[str, object]:
    close = previous.get("close")
    return {
        "source": previous.get("source", ""),
        "asset_type": previous.get("asset_type", "equity"),
        "symbol": previous.get("symbol", ""),
        "timeframe": previous.get("timeframe", "1d"),
        "ts": f"{day}T00:00:00+00:00",
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 0.0,
        "missing_ohlcv": True,
        "stale_price": True,
        "zero_volume": True,
        "price_jump": False,
        "invalid_spread": False,
        "incomplete_lob": False,
        "timezone_adjusted": False,
        "imputed": True,
    }


def _group_symbol_timeframe(rows: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (str(row.get("symbol") or ""), str(row.get("timeframe") or ""))
        grouped.setdefault(key, []).append(dict(row))
    return grouped


def _calendar_for_group(
    rows: Sequence[Mapping[str, object]],
    explicit_calendar: Sequence[str] | None,
) -> list[str]:
    if explicit_calendar:
        return sorted(str(day)[:10] for day in explicit_calendar)
    dates = [_timestamp(row["ts"]).date() for row in rows]
    if not dates:
        return []
    start = min(dates)
    end = max(dates)
    days = (end - start).days
    return [(start + timedelta(days=offset)).isoformat() for offset in range(days + 1)]


def _sort_key(row: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
        str(row.get("ts") or ""),
        str(row.get("source") or ""),
    )


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
