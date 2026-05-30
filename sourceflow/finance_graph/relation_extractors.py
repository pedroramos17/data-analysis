"""Relation extractor helpers for financial graph edges."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def same_sector_edges(rows: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Create same-sector relation edges from instrument metadata.

    Example:
        `edges = same_sector_edges(rows)`
    """
    groups = _group_by(rows, "sector")
    return _complete_group_edges(groups, "same_sector")


def same_industry_edges(
    rows: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Create same-industry relation edges from instrument metadata.

    Example:
        `edges = same_industry_edges(rows)`
    """
    groups = _group_by(rows, "industry")
    return _complete_group_edges(groups, "same_industry")


def _group_by(
    rows: Iterable[Mapping[str, object]],
    key: str,
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        symbol = str(row.get("symbol", "")).strip()
        if value and symbol:
            groups.setdefault(value, []).append(symbol)
    return groups


def _complete_group_edges(
    groups: Mapping[str, list[str]],
    relation_type: str,
) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    for symbols in groups.values():
        edges.extend(_pair_edges(symbols, relation_type))
    return edges


def _pair_edges(symbols: list[str], relation_type: str) -> list[dict[str, object]]:
    return [
        {"source": left, "target": right, "relation_type": relation_type, "weight": 1.0}
        for left in symbols
        for right in symbols
        if left != right
    ]
