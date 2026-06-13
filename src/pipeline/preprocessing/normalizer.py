"""Final normalization helpers for preprocessed rows."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence


def normalize_output_rows(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Return deterministic, JSON-safe output rows."""
    return [_normalize_row(row) for row in sorted(rows, key=_sort_key)]


def normalize_quality_report(report: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic quality-report payload."""
    return json.loads(json.dumps(dict(report), sort_keys=True, default=str))


def _normalize_row(row: Mapping[str, object]) -> dict[str, object]:
    item = {str(key): _json_safe(value) for key, value in row.items()}
    flags = item.get("quality_flags")
    if isinstance(flags, list):
        item["quality_flags"] = sorted(str(flag) for flag in flags)
    return item


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _sort_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
        str(row.get("ts") or ""),
    )
