"""Forward time validation for symbolic factors."""

from __future__ import annotations

from sourceflow.intelligence.evaluation.objectives import objective_value
from sourceflow.intelligence.factor_base.types import FactorScore


def evaluate_forward_window(
    rows: list[dict[str, object]],
    objective: str,
    threshold: float = 0.5,
) -> FactorScore:
    """Evaluate factor usefulness against future-only objective rows.

    Example:
        `score = evaluate_forward_window(rows, "future_event_growth", 0.5)`
    """
    factor_name = _first_factor_column(rows, objective)
    utility = _utility(rows, factor_name, objective, threshold)
    novelty = _novelty(rows, factor_name)
    return FactorScore(factor_name, objective, utility, 1.0, novelty, 1, 0.0)


def split_forward_windows(
    rows: list[dict[str, object]],
    folds: int = 3,
) -> tuple[list[dict[str, object]], ...]:
    """Split rows by time order for forward validation.

    Example:
        `windows = split_forward_windows(rows, folds=3)`
    """
    ordered = sorted(rows, key=lambda row: str(row.get("as_of", "")))
    size = max(1, len(ordered) // max(1, folds))
    return tuple(
        ordered[index : index + size] for index in range(0, len(ordered), size)
    )


def _first_factor_column(rows: list[dict[str, object]], objective: str) -> str:
    excluded = {"entity_id", "as_of", objective}
    for key in rows[0]:
        if key not in excluded:
            return key
    raise ValueError(f"Invalid rows {rows}; expected at least one factor column")


def _utility(
    rows: list[dict[str, object]],
    factor_name: str,
    objective: str,
    threshold: float,
) -> float:
    hits = 0
    considered = 0
    for row in rows:
        considered += int(float(row.get(factor_name, 0) or 0) >= threshold)
        hits += int(_is_hit(row, factor_name, objective, threshold))
    return hits / max(1, considered)


def _is_hit(
    row: dict[str, object],
    factor_name: str,
    objective: str,
    threshold: float,
) -> bool:
    factor_value = float(row.get(factor_name, 0) or 0)
    return factor_value >= threshold and objective_value(row, objective) >= threshold


def _novelty(rows: list[dict[str, object]], factor_name: str) -> float:
    values = {round(float(row.get(factor_name, 0) or 0), 3) for row in rows}
    return len(values) / max(1, len(rows))
