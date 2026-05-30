"""Typed mutation operators for symbolic formulas."""

from __future__ import annotations

import random

from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.search.random_search import generate_random_formulas
from sourceflow.intelligence.symbolic.expression import (
    FormulaExpression,
    binary,
    post_process,
)
from sourceflow.intelligence.symbolic.validator import validate_formula


def mutate_formula(
    expression: FormulaExpression,
    constraints: SearchConstraints,
    rng: random.Random,
) -> FormulaExpression:
    """Return a valid bounded mutation of one formula.

    Example:
        `mutated = mutate_formula(expression, SearchConstraints(), random.Random(7))`
    """
    candidate = _mutation_candidate(expression, constraints, rng)
    if validate_formula(candidate, constraints).is_valid:
        return candidate
    return expression


def _mutation_candidate(
    expression: FormulaExpression,
    constraints: SearchConstraints,
    rng: random.Random,
) -> FormulaExpression:
    replacement = generate_random_formulas(
        1, constraints, seed=rng.randint(1, 1_000_000)
    )[0]
    if rng.random() < 0.35:
        return replacement
    if rng.random() < 0.65:
        return post_process("rank", expression)
    return binary(rng.choice(("add", "sub", "max")), expression, replacement)
