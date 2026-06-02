"""Multi-objective formula scoring."""

from __future__ import annotations

from sourceflow.intelligence.evaluation.leakage import leakage_score
from sourceflow.intelligence.factor_base.types import FactorScore
from sourceflow.intelligence.symbolic.expression import (
    FormulaExpression,
    operator_count,
)


def score_formula(
    factor_name: str,
    objective: str,
    expression: FormulaExpression,
    utility: float,
    stability: float,
    novelty: float,
) -> FactorScore:
    """Score a symbolic formula with utility, stability, novelty, and penalties.

    Example:
        `score = score_formula("candidate", "future_event_growth", expr, .5, .5, .5)`
    """
    complexity = operator_count(expression)
    leakage = leakage_score(expression)
    return FactorScore(
        factor_name, objective, utility, stability, novelty, complexity, leakage
    )
