"""Shared reproducibility metadata helpers for Quant4 run records."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

DateRange = tuple[date, date]


def build_run_metadata_fields(
    data_range: DateRange,
    split_range: DateRange,
    random_seed: int = 0,
    provenance: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return validated model kwargs for reproducible Quant4 runs.

    Example:
        `build_run_metadata_fields((d1, d2), (d2, d2), 7, {"source": "test"})`
    """
    data_start, data_end = validate_date_range("data_range", data_range)
    split_start, split_end = validate_date_range("split_range", split_range)
    _validate_split_inside_data(data_start, data_end, split_start, split_end)
    return {
        "random_seed": random_seed,
        "data_start": data_start,
        "data_end": data_end,
        "split_start": split_start,
        "split_end": split_end,
        "provenance_json": dict(provenance or {}),
    }


def parse_iso_date_range(
    start_value: object,
    end_value: object,
    label: str,
) -> DateRange:
    """Parse an ISO date range for command-line run metadata.

    Example:
        `parse_iso_date_range("2024-01-01", "2024-01-31", "data_range")`
    """
    try:
        parsed = (
            date.fromisoformat(str(start_value)),
            date.fromisoformat(str(end_value)),
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid {label} {(start_value, end_value)!r}; "
            "expected ISO date pair YYYY-MM-DD"
        ) from exc
    return validate_date_range(label, parsed)


def validate_date_range(label: str, value: object) -> DateRange:
    """Validate a date range tuple and return normalized dates.

    Example:
        `validate_date_range("split_range", (start_date, end_date))`
    """
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f"Invalid {label} {value!r}; expected tuple[date, date]")
    start_value, end_value = value
    if not isinstance(start_value, date) or not isinstance(end_value, date):
        raise ValueError(f"Invalid {label} {value!r}; expected tuple[date, date]")
    if start_value > end_value:
        raise ValueError(f"Invalid {label} {value!r}; expected start <= end")
    return start_value, end_value


def _validate_split_inside_data(
    data_start: date,
    data_end: date,
    split_start: date,
    split_end: date,
) -> None:
    if split_start < data_start or split_end > data_end:
        raise ValueError(
            f"Invalid split_range {(split_start, split_end)!r}; "
            f"expected dates within data_range {(data_start, data_end)!r}"
        )
