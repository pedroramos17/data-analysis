"""Independent leakage checks for formulas and evaluation rows."""

from __future__ import annotations

from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.symbolic.expression import FormulaExpression
from sourceflow.intelligence.symbolic.validator import validate_formula


def leakage_score(expression: FormulaExpression) -> float:
    """Return 1.0 when a formula leaks future-only data.

    Example:
        `score = leakage_score(expression)`
    """
    validation = validate_formula(expression, SearchConstraints())
    return 0.0 if validation.is_valid else _has_leakage(validation.errors)


def rows_respect_availability(rows: list[dict[str, object]]) -> bool:
    """Return whether rows expose non-future availability metadata.

    Example:
        `ok = rows_respect_availability(rows)`
    """
    for row in rows:
        if (
            "available_at" in row
            and "as_of" in row
            and row["available_at"] > row["as_of"]
        ):
            return False
    return True


def _has_leakage(errors: tuple[str, ...]) -> float:
    return 1.0 if any("Leakage" in error for error in errors) else 0.0
