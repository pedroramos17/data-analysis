"""Data quality checks for Quant4 dataset metadata."""

from __future__ import annotations


def validate_dataset_identity(name: str, source: str, frequency: str) -> None:
    """Validate required dataset identity fields.

    Example:
        `validate_dataset_identity("spy-daily", "local-csv", "1d")`
    """
    for label, value in _identity_values(name, source, frequency):
        if value.strip():
            continue
        raise ValueError(f"Invalid dataset {label} {value!r}; expected non-empty text")


def _identity_values(
    name: str,
    source: str,
    frequency: str,
) -> tuple[tuple[str, str], ...]:
    return (("name", name), ("source", source), ("frequency", frequency))
