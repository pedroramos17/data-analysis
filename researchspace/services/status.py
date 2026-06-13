"""Support and workflow status helpers for ResearchSpace."""

from __future__ import annotations

SUPPORT_STATUS_CHOICES: tuple[tuple[str, str], ...] = (
    ("SUPPORTED", "Supported"),
    ("PARTIAL", "Partial"),
    ("UNSUPPORTED", "Unsupported"),
    ("NEEDS_REVIEW", "Needs review"),
)
SUPPORT_STATUS_VALUES = frozenset(value for value, _label in SUPPORT_STATUS_CHOICES)


def normalize_support_status(value: object) -> str:
    """Return a safe support status label.

    Example:
        `normalize_support_status("supported")`
    """
    normalized = str(value or "").strip().upper()
    if normalized in SUPPORT_STATUS_VALUES:
        return normalized
    return "NEEDS_REVIEW"


def support_status_choices() -> tuple[tuple[str, str], ...]:
    """Return model choices for support status fields.

    Example:
        `choices=support_status_choices()`
    """
    return SUPPORT_STATUS_CHOICES
