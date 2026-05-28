"""Population helpers for genetic symbolic formula search."""

from __future__ import annotations

import random
from dataclasses import dataclass

from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.search.random_search import generate_random_formulas
from sourceflow.intelligence.symbolic.expression import FormulaExpression


@dataclass(frozen=True, slots=True)
class FormulaPopulation:
    """A deterministic GP population snapshot.

    Example:
        `population = initialize_population(20, constraints, random.Random(1))`
    """

    formulas: tuple[FormulaExpression, ...]


def initialize_population(
    size: int,
    constraints: SearchConstraints,
    rng: random.Random,
) -> FormulaPopulation:
    """Create a valid initial population.

    Example:
        `population = initialize_population(100, constraints, random.Random(9))`
    """
    formulas = generate_random_formulas(
        size, constraints, seed=rng.randint(1, 1_000_000)
    )
    return FormulaPopulation(formulas)


def tournament_selection(
    formulas: tuple[FormulaExpression, ...],
    scores: tuple[float, ...],
    rng: random.Random,
) -> FormulaExpression:
    """Select one formula by deterministic two-way tournament.

    Example:
        `winner = tournament_selection(formulas, scores, random.Random(1))`
    """
    left, right = rng.sample(range(len(formulas)), 2)
    return formulas[left] if scores[left] >= scores[right] else formulas[right]


def elitism(
    formulas: tuple[FormulaExpression, ...],
    scores: tuple[float, ...],
    count: int,
) -> tuple[FormulaExpression, ...]:
    """Return highest-scoring formulas unchanged.

    Example:
        `elite = elitism(formulas, scores, 2)`
    """
    ranked = sorted(
        zip(scores, formulas, strict=True), key=lambda item: item[0], reverse=True
    )
    return tuple(formula for _score, formula in ranked[:count])
