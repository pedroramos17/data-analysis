"""Deterministic genetic programming search for symbolic formulas."""

from __future__ import annotations

import random
from dataclasses import dataclass

from django.db import connection as django_connection

from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.factor_base.types import FactorDefinition
from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.search.crossover import crossover_formulas
from sourceflow.intelligence.search.mutation import mutate_formula
from sourceflow.intelligence.search.population import (
    elitism,
    initialize_population,
    tournament_selection,
)
from sourceflow.intelligence.search.random_search import FactorCandidateResult
from sourceflow.intelligence.search.scorer import score_formula
from sourceflow.intelligence.symbolic.compiler import (
    FactorExecutionContext,
    compile_formula,
)
from sourceflow.intelligence.symbolic.expression import FormulaExpression


@dataclass(frozen=True, slots=True)
class GeneticSearchResult:
    """Summary for a GP symbolic search run.

    Example:
        `result = run_genetic_search(100, 20, constraints, context, "growth")`
    """

    generations_completed: int
    best_scores: tuple[float, ...]
    accepted: tuple[FactorCandidateResult, ...]


def run_genetic_search(
    population_size: int,
    generations: int,
    constraints: SearchConstraints,
    context: FactorExecutionContext,
    objective: str,
    seed: int = 1,
) -> GeneticSearchResult:
    """Run deterministic typed genetic programming search.

    Example:
        `run_genetic_search(20, 5, constraints, context, "future_claim_conflict")`
    """
    rng = random.Random(seed)
    population = initialize_population(population_size, constraints, rng).formulas
    best_scores: list[float] = []
    accepted: list[FactorCandidateResult] = []
    for generation in range(generations):
        population, candidate = _next_generation(
            population, constraints, context, objective, rng, generation, seed
        )
        best_scores.append(_monotonic_best(best_scores, candidate.score.final_score))
        accepted.append(candidate)
    _persist_candidates(accepted, context)
    return GeneticSearchResult(generations, tuple(best_scores), tuple(accepted))


def _next_generation(
    population: tuple[FormulaExpression, ...],
    constraints: SearchConstraints,
    context: FactorExecutionContext,
    objective: str,
    rng: random.Random,
    generation: int,
    seed: int,
) -> tuple[tuple[FormulaExpression, ...], FactorCandidateResult]:
    scores = tuple(
        _fitness(index, formula, constraints, context, objective)
        for index, formula in enumerate(population)
    )
    candidate = _best_candidate(population, scores, objective, generation, seed)
    elite_count = max(1, int(len(population) * 0.05))
    next_population = list(elitism(population, scores, elite_count))
    while len(next_population) < len(population):
        next_population.append(_child(population, scores, constraints, rng))
    return tuple(next_population), candidate


def _child(
    population: tuple[FormulaExpression, ...],
    scores: tuple[float, ...],
    constraints: SearchConstraints,
    rng: random.Random,
) -> FormulaExpression:
    left = tournament_selection(population, scores, rng)
    right = tournament_selection(population, scores, rng)
    crossed = crossover_formulas(left, right, constraints, rng)
    return mutate_formula(crossed, constraints, rng)


def _fitness(
    index: int,
    expression: FormulaExpression,
    constraints: SearchConstraints,
    context: FactorExecutionContext,
    objective: str,
) -> float:
    plan = compile_formula(
        f"candidate_gp_tmp_{index}",
        expression,
        constraints=constraints,
        context=context,
    )
    values = plan.execute(context.operand_frame).fillna(0)
    utility = _utility(values, context, objective)
    stability = max(0.0, 1.0 - float(values.std() or 0) * 0.05)
    score = score_formula(
        "candidate_gp_tmp", objective, expression, utility, stability, 0.3
    )
    return max(0.0, score.final_score)


def _utility(values: object, context: FactorExecutionContext, objective: str) -> float:
    if objective not in context.operand_frame:
        return 0.25
    labels = context.operand_frame[objective].fillna(0)
    if values.nunique() < 2 or labels.nunique() < 2:
        return 0.25
    return abs(float(values.corr(labels) or 0))


def _best_candidate(
    population: tuple[FormulaExpression, ...],
    scores: tuple[float, ...],
    objective: str,
    generation: int,
    seed: int,
) -> FactorCandidateResult:
    best_index = max(range(len(population)), key=lambda index: scores[index])
    expression = population[best_index]
    factor_score = score_formula(
        f"candidate_gp_{seed}_{generation}",
        objective,
        expression,
        scores[best_index],
        0.5,
        0.3,
    )
    return FactorCandidateResult(
        f"candidate_gp_{seed}_{generation}", expression, factor_score
    )


def _monotonic_best(best_scores: list[float], candidate_score: float) -> float:
    if not best_scores:
        return candidate_score
    return max(best_scores[-1], candidate_score)


def _persist_candidates(
    accepted: list[FactorCandidateResult],
    context: FactorExecutionContext,
) -> None:
    registry = FactorRegistry(context.connection or django_connection)
    for candidate in accepted:
        registry.register_factor(_candidate_definition(candidate))


def _candidate_definition(candidate: FactorCandidateResult) -> FactorDefinition:
    return FactorDefinition(
        candidate.name,
        "Generated GP comparison and propagation candidate.",
        candidate.expression,
        "event",
        status="candidate",
        source="gp",
    )
