"""Dependency extraction from symbolic expression trees."""

from __future__ import annotations

from sourceflow.intelligence.factor_base.types import FactorDefinition, FactorDependency
from sourceflow.intelligence.symbolic.expression import (
    FormulaExpression,
    OperandRef,
    walk_expression,
)
from sourceflow.intelligence.symbolic.grammar import OperandType


def expression_dependencies(expression: FormulaExpression) -> tuple[str, ...]:
    """Return factor dependencies referenced by an expression.

    Example:
        `deps = expression_dependencies(factor("event_conflict_risk"))`
    """
    names = [
        node.name
        for node in walk_expression(expression)
        if isinstance(node, OperandRef) and node.operand_type == OperandType.FACTOR
    ]
    return tuple(dict.fromkeys(names))


def factor_dependencies(definition: FactorDefinition) -> tuple[FactorDependency, ...]:
    """Return dependency rows for a factor definition.

    Example:
        `rows = factor_dependencies(definition)`
    """
    dependencies = expression_dependencies(definition.expression)
    return tuple(
        FactorDependency(definition.name, dependency, "factor")
        for dependency in dependencies
    )
