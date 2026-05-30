"""Browser-triggered Sourceflow intelligence workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from sourceflow.intelligence.evaluation.forward_validation import (
    evaluate_forward_window,
)
from sourceflow.intelligence.evaluation.objectives import (
    is_objective_name,
    objective_names,
)
from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.factor_base.storage import FactorValueStorage
from sourceflow.intelligence.factor_base.types import FactorScore
from sourceflow.intelligence.runtime import compute_seed_factor_values
from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.search.random_search import generate_random_formulas
from sourceflow.intelligence.seeds import seed_factor_definitions
from sourceflow.intelligence.symbolic.expression import formula_text


@dataclass(frozen=True, slots=True)
class IntelligenceActionResult:
    """A UI-safe action result.

    Example:
        `result = IntelligenceActionResult("Registered 18 factors", 18)`
    """

    message: str
    count: int
    preview: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntelligenceComputeWindow:
    """Time bounds for leakage-safe factor computation.

    Example:
        `window = compute_window_from_text("", "", "")`
    """

    as_of: datetime
    history_start: datetime
    history_end: datetime


def register_seed_factors_action(connection: object) -> IntelligenceActionResult:
    """Register all typed seed factor definitions.

    Example:
        `result = register_seed_factors_action(connection)`
    """
    count = FactorRegistry(connection).register_factors(seed_factor_definitions())
    return IntelligenceActionResult(f"Registered {count} symbolic factors", count)


def compute_seed_factors_action(
    connection: object,
    output_dir: Path,
    as_of_text: str,
    history_start_text: str,
    history_end_text: str,
) -> IntelligenceActionResult:
    """Compute seed factor values for a bounded historical window.

    Example:
        `result = compute_seed_factors_action(conn, path, "", "", "")`
    """
    window = compute_window_from_text(as_of_text, history_start_text, history_end_text)
    paths = compute_seed_factor_values(
        connection, output_dir, window.as_of, window.history_start, window.history_end
    )
    return IntelligenceActionResult(
        f"Computed {len(paths)} symbolic factors", len(paths)
    )


def generate_formula_preview_action(
    count: int,
    seed: int,
    preview_limit: int = 20,
) -> IntelligenceActionResult:
    """Generate grammar-valid random formulas without persisting them.

    Example:
        `result = generate_formula_preview_action(500, 7)`
    """
    formulas = generate_random_formulas(count, SearchConstraints(), seed=seed)
    preview = tuple(formula_text(item) for item in formulas[:preview_limit])
    return IntelligenceActionResult(
        f"Generated {len(formulas)} valid formulas", count, preview
    )


def evaluate_factor_action(
    connection: object,
    output_dir: Path,
    factor_name: str,
    objective: str,
) -> IntelligenceActionResult:
    """Evaluate a persisted factor artifact against a future-only objective.

    Example:
        `result = evaluate_factor_action(conn, path, "coverage", "future_event_growth")`
    """
    _validate_objective(objective)
    rows = evaluation_rows(output_dir, factor_name, objective)
    if not rows:
        return IntelligenceActionResult(f"No values found for {factor_name}", 0)
    score = evaluate_forward_window(rows, objective)
    FactorRegistry(connection).record_factor_evaluation(score)
    return _evaluation_result(score, len(rows))


def evaluation_rows(
    output_dir: Path,
    factor_name: str,
    objective: str,
) -> list[dict[str, object]]:
    """Build evaluation rows from the latest persisted factor values.

    Example:
        `rows = evaluation_rows(path, "coverage_intensity", "future_event_growth")`
    """
    storage = FactorValueStorage(output_dir / "factors")
    path = storage.latest_path(factor_name)
    if path is None:
        return []
    return [
        _evaluation_row(row, factor_name, objective)
        for row in storage.read_values(path)
        if objective in row
    ]


def compute_window_from_text(
    as_of_text: str,
    history_start_text: str,
    history_end_text: str,
) -> IntelligenceComputeWindow:
    """Parse UI time bounds with command-equivalent defaults.

    Example:
        `window = compute_window_from_text("", "", "")`
    """
    as_of = parsed_intelligence_datetime(as_of_text) or timezone.now()
    history_end = parsed_intelligence_datetime(history_end_text) or as_of
    history_start = parsed_intelligence_datetime(
        history_start_text
    ) or history_end - timedelta(hours=72)
    return IntelligenceComputeWindow(as_of, history_start, history_end)


def parsed_intelligence_datetime(value: str) -> datetime | None:
    """Parse an ISO datetime entered in the UI.

    Example:
        `parsed = parsed_intelligence_datetime("2026-05-24T12:00:00Z")`
    """
    if not value:
        return None
    try:
        return parse_datetime(value) or datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid datetime {value}; expected ISO-8601 datetime"
        ) from error


def _validate_objective(objective: str) -> None:
    if is_objective_name(objective):
        return
    expected = ", ".join(objective_names())
    raise ValueError(f"Invalid objective {objective}; expected one of {expected}")


def _evaluation_row(
    row: dict[str, object],
    factor_name: str,
    objective: str,
) -> dict[str, object]:
    value = float(row.get("value", 0) or 0)
    return {
        "entity_id": row.get("entity_id", ""),
        "as_of": row.get("as_of", ""),
        factor_name: value,
        objective: float(row.get(objective, 0) or 0),
    }


def _evaluation_result(score: FactorScore, row_count: int) -> IntelligenceActionResult:
    message = f"Evaluated {score.factor_name} on {row_count} rows"
    return IntelligenceActionResult(message, row_count)
