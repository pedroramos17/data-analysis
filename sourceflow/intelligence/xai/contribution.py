"""Operand contribution summaries for factor scores."""

from __future__ import annotations


def top_operand_contributions(
    operands: dict[str, float],
    limit: int = 5,
) -> tuple[tuple[str, float], ...]:
    """Return the largest absolute operand contributions.

    Example:
        `top = top_operand_contributions({"coverage": 0.8})`
    """
    ranked = sorted(operands.items(), key=lambda item: abs(item[1]), reverse=True)
    return tuple(ranked[:limit])
