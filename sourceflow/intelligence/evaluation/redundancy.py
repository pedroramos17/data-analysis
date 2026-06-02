"""Correlation and mutual-information redundancy checks."""

from __future__ import annotations

import pandas as pd

from sourceflow.intelligence.evaluation.objectives import is_objective_name


def find_redundant_factors(
    rows: list[dict[str, object]],
    threshold: float = 0.95,
) -> tuple[tuple[str, str], ...]:
    """Return factor pairs whose values are highly redundant.

    Example:
        `pairs = find_redundant_factors(rows, threshold=0.95)`
    """
    frame = pd.DataFrame(rows)
    factors = _numeric_factor_columns(frame)
    redundant: list[tuple[str, str]] = []
    for index, left in enumerate(factors):
        redundant.extend(
            _redundant_for_left(frame, factors[index + 1 :], left, threshold)
        )
    return tuple(redundant)


def mutual_information_score(
    rows: list[dict[str, object]],
    left: str,
    right: str,
) -> float:
    """Return a cheap discretized mutual-information proxy.

    Example:
        `score = mutual_information_score(rows, "a", "b")`
    """
    frame = pd.DataFrame(rows)
    left_bins = pd.qcut(frame[left], q=min(3, len(frame)), duplicates="drop")
    right_bins = pd.qcut(frame[right], q=min(3, len(frame)), duplicates="drop")
    return float((left_bins.astype(str) == right_bins.astype(str)).mean())


def _numeric_factor_columns(frame: pd.DataFrame) -> list[str]:
    columns = []
    for column in frame.select_dtypes(include="number").columns:
        if not is_objective_name(str(column)):
            columns.append(str(column))
    return columns


def _redundant_for_left(
    frame: pd.DataFrame,
    candidates: list[str],
    left: str,
    threshold: float,
) -> list[tuple[str, str]]:
    redundant: list[tuple[str, str]] = []
    for right in candidates:
        correlation = float(frame[left].corr(frame[right]) or 0)
        if abs(correlation) >= threshold:
            redundant.append((left, right))
    return redundant
