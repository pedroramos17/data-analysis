"""Future-only objective helpers for factor evaluation."""

from __future__ import annotations

OBJECTIVE_NAMES = (
    "future_event_growth",
    "future_provider_spread",
    "future_claim_conflict",
    "alert_feedback",
)


def objective_names() -> tuple[str, ...]:
    """Return supported future-only objective names.

    Example:
        `names = objective_names()`
    """
    return OBJECTIVE_NAMES


def is_objective_name(name: str) -> bool:
    """Return whether a column is a future-only objective.

    Example:
        `is_objective_name("future_event_growth")`
    """
    return name in OBJECTIVE_NAMES


def objective_value(row: dict[str, object], objective: str) -> float:
    """Return a bounded objective value from an evaluation row.

    Example:
        `value = objective_value(row, "future_event_growth")`
    """
    value = row.get(objective, 0.0)
    return max(0.0, min(1.0, float(value or 0)))
