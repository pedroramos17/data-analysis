"""FRED official API normalization."""

from __future__ import annotations

from collections.abc import Mapping

from sourceflow.config.feature_flags import require_feature


def normalize_observations(
    series_id: str,
    payload: Mapping[str, object],
) -> list[dict[str, object]]:
    """Normalize FRED series observation payloads.

    Example:
        `rows = normalize_observations("GDP", payload)`
    """
    require_feature("FIN_DATA_FRED")
    observations = payload.get("observations", [])
    if not isinstance(observations, list):
        return []
    return [_row(series_id, item) for item in observations if _valid_item(item)]


def normalize_series_metadata(payload: Mapping[str, object]) -> list[dict[str, object]]:
    """Normalize FRED series metadata rows.

    Example:
        `rows = normalize_series_metadata(payload)`
    """
    require_feature("FIN_DATA_FRED")
    rows = payload.get("seriess", payload.get("series", []))
    if not isinstance(rows, list):
        return []
    return [_metadata_row(row) for row in rows if isinstance(row, dict)]


def _valid_item(item: object) -> bool:
    return isinstance(item, dict) and item.get("value") not in (None, ".", "")


def _row(series_id: str, item: Mapping[str, object]) -> dict[str, object]:
    return {
        "series_id": series_id,
        "date": str(item.get("date", "")),
        "value": float(str(item.get("value")).replace(",", "")),
        "realtime_start": str(item.get("realtime_start", "")),
        "realtime_end": str(item.get("realtime_end", "")),
        "raw_payload_json": dict(item),
    }


def _metadata_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "provider": "FRED",
        "series_id": str(row.get("id", "")),
        "title": str(row.get("title", "")),
        "frequency": str(row.get("frequency", "")),
        "units": str(row.get("units", "")),
        "seasonal_adjustment": str(row.get("seasonal_adjustment", "")),
        "source_notes": str(row.get("notes", "")),
    }
