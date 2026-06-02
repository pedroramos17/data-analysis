"""Typed crossover operators for symbolic formulas."""

from __future__ import annotations

import random

from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.symbolic.expression import FormulaExpression, binary
from sourceflow.intelligence.symbolic.validator import validate_formula


def crossover_formulas(
    left: FormulaExpression,
    right: FormulaExpression,
    constraints: SearchConstraints,
    rng: random.Random,
) -> FormulaExpression:
    """Swap compatible numeric formula subtrees.

    Example:
        `child = crossover_formulas(left, right, constraints, random.Random(3))`
    """
    operator_name = rng.choice(("add", "max", "div_safe"))
    candidate = binary(operator_name, left, right)
    if validate_formula(candidate, constraints).is_valid:
        return candidate
    return left
