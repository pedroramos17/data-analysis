"""Grammar-constrained random symbolic formula generation and search."""

from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd
from django.db import connection as django_connection

from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.factor_base.types import FactorDefinition, FactorScore
from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.search.scorer import score_formula
from sourceflow.intelligence.symbolic.compiler import (
    FactorExecutionContext,
    compile_formula,
)
from sourceflow.intelligence.symbolic.expression import (
    FormulaExpression,
    binary,
    const,
    factor,
    operand,
    post_process,
    unary,
)
from sourceflow.intelligence.symbolic.grammar import (
    factor_operand_names,
    numeric_operand_names,
)
from sourceflow.intelligence.symbolic.validator import validate_formula

UNARY_OPERATORS = ("log1p", "sqrt", "abs", "zscore", "rank")
BINARY_OPERATORS = ("add", "sub", "mul", "div_safe", "max", "min")


@dataclass(frozen=True, slots=True)
class FactorCandidateResult:
    """One accepted generated candidate.

    Example:
        `result = FactorCandidateResult("candidate", expression, score)`
    """

    name: str
    expression: FormulaExpression
    score: FactorScore


@dataclass(frozen=True, slots=True)
class FactorSearchResult:
    """Summary for a symbolic search run.

    Example:
        `summary = run_random_search(500, constraints, context, "growth")`
    """

    generated_count: int
    accepted: tuple[FactorCandidateResult, ...]
    rejected_count: int

    @property
    def accepted_count(self) -> int:
        """Return accepted candidate count.

        Example:
            `summary.accepted_count`
        """
        return len(self.accepted)


def generate_random_formulas(
    count: int,
    constraints: SearchConstraints,
    seed: int = 1,
) -> tuple[FormulaExpression, ...]:
    """Generate valid random formulas from the typed grammar.

    Example:
        `formulas = generate_random_formulas(500, SearchConstraints(), seed=7)`
    """
    rng = random.Random(seed)
    formulas: list[FormulaExpression] = []
    while len(formulas) < count:
        expression = _random_formula(rng, constraints)
        if validate_formula(expression, constraints).is_valid:
            formulas.append(expression)
    return tuple(formulas)


def run_random_search(
    count: int,
    constraints: SearchConstraints,
    context: FactorExecutionContext,
    objective: str,
    seed: int = 1,
) -> FactorSearchResult:
    """Generate, evaluate, filter, and persist accepted candidates.

    Example:
        `result = run_random_search(500, constraints, context, "future_event_growth")`
    """
    registry = FactorRegistry(context.connection or django_connection)
    formulas = generate_random_formulas(count, constraints, seed)
    accepted = _accepted_candidates(formulas, constraints, context, objective, seed)
    for candidate in accepted:
        registry.register_factor(_candidate_definition(candidate))
    return FactorSearchResult(count, tuple(accepted), count - len(accepted))


def _accepted_candidates(
    formulas: tuple[FormulaExpression, ...],
    constraints: SearchConstraints,
    context: FactorExecutionContext,
    objective: str,
    seed: int,
) -> list[FactorCandidateResult]:
    accepted: list[FactorCandidateResult] = []
    for index, expression in enumerate(formulas):
        candidate = _evaluate_candidate(
            index, expression, constraints, context, objective, seed
        )
        if candidate is not None:
            accepted.append(candidate)
        if len(accepted) >= min(25, len(formulas)):
            return accepted
    return accepted


def _evaluate_candidate(
    index: int,
    expression: FormulaExpression,
    constraints: SearchConstraints,
    context: FactorExecutionContext,
    objective: str,
    seed: int,
) -> FactorCandidateResult | None:
    values = _candidate_values(index, expression, constraints, context)
    if not _passes_output_filters(values, constraints):
        return None
    score = _candidate_score(index, expression, values, context, objective, seed)
    if score.final_score < 0:
        return None
    return FactorCandidateResult(f"candidate_random_{seed}_{index}", expression, score)


def _candidate_values(
    index: int,
    expression: FormulaExpression,
    constraints: SearchConstraints,
    context: FactorExecutionContext,
) -> pd.Series:
    plan = compile_formula(
        f"candidate_random_tmp_{index}",
        expression,
        constraints=constraints,
        context=context,
    )
    return plan.execute(context.operand_frame)


def _passes_output_filters(values: pd.Series, constraints: SearchConstraints) -> bool:
    missing_ratio = float(values.isna().mean()) if len(values) else 1.0
    if missing_ratio > constraints.max_missing_ratio:
        return False
    return int(values.fillna(0).nunique()) >= constraints.min_unique_values


def _candidate_score(
    index: int,
    expression: FormulaExpression,
    values: pd.Series,
    context: FactorExecutionContext,
    objective: str,
    seed: int,
) -> FactorScore:
    utility = _objective_utility(values, context.operand_frame, objective)
    stability = max(0.0, 1.0 - float(values.fillna(0).std() or 0) * 0.05)
    novelty = 0.2 + ((index + seed) % 5) * 0.05
    return score_formula(
        f"candidate_random_{seed}_{index}",
        objective,
        expression,
        utility,
        stability,
        novelty,
    )


def _objective_utility(
    values: pd.Series,
    frame: pd.DataFrame,
    objective: str,
) -> float:
    if objective not in frame:
        return 0.25
    label = pd.to_numeric(frame[objective], errors="coerce").fillna(0)
    factor_values = pd.to_numeric(values, errors="coerce").fillna(0)
    if factor_values.nunique() < 2 or label.nunique() < 2:
        return 0.25
    return abs(float(factor_values.corr(label) or 0))


def _candidate_definition(candidate: FactorCandidateResult) -> FactorDefinition:
    return FactorDefinition(
        candidate.name,
        "Generated comparison and propagation candidate.",
        candidate.expression,
        "event",
        status="candidate",
        source="random",
    )


def _random_formula(
    rng: random.Random,
    constraints: SearchConstraints,
) -> FormulaExpression:
    expression = _random_leaf(rng, constraints)
    max_steps = rng.randint(0, max(0, constraints.max_depth - 1))
    for _step in range(min(max_steps, constraints.max_operators)):
        expression = _wrap_expression(rng, expression, constraints)
    return expression


def _random_leaf(
    rng: random.Random,
    constraints: SearchConstraints,
) -> FormulaExpression:
    if rng.random() < 0.25:
        return factor(rng.choice(factor_operand_names()))
    operands = constraints.allowed_operands or numeric_operand_names()
    return operand(rng.choice(tuple(operands)))


def _wrap_expression(
    rng: random.Random,
    expression: FormulaExpression,
    constraints: SearchConstraints,
) -> FormulaExpression:
    roll = rng.random()
    if roll < 0.35:
        return unary(rng.choice(UNARY_OPERATORS[:3]), expression)
    if roll < 0.55:
        return post_process(rng.choice(UNARY_OPERATORS[3:]), expression)
    right = _random_leaf(rng, constraints)
    if rng.random() < 0.20:
        right = const(float(rng.randint(1, 5)))
    return binary(rng.choice(BINARY_OPERATORS), expression, right)
