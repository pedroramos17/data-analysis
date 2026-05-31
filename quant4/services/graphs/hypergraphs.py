"""Hypergraph grouping helpers for Quant4 topology research."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HypergraphResult:
    """Metadata-derived hyperedges by group name.

    Example:
        `HypergraphResult({"sector:Tech": ["AAA"]})`
    """

    hyperedges: dict[str, list[str]]


class HypergraphBuilder:
    """Build sector, index, and regime hyperedges from asset metadata."""

    def build(
        self,
        asset_metadata: Mapping[str, Mapping[str, object]],
    ) -> HypergraphResult:
        """Return grouped hyperedges when metadata exists."""
        hyperedges: dict[str, list[str]] = {}
        for symbol, metadata in asset_metadata.items():
            _add_metadata_group(hyperedges, "sector", symbol, metadata)
            _add_metadata_group(hyperedges, "index", symbol, metadata)
            _add_metadata_group(hyperedges, "regime", symbol, metadata)
        return HypergraphResult(_sorted_groups(hyperedges))


def _add_metadata_group(
    hyperedges: dict[str, list[str]],
    field: str,
    symbol: str,
    metadata: Mapping[str, object],
) -> None:
    value = str(metadata.get(field, "")).strip()
    if not value:
        return
    hyperedges.setdefault(f"{field}:{value}", []).append(str(symbol))


def _sorted_groups(hyperedges: Mapping[str, list[str]]) -> dict[str, list[str]]:
    return {name: sorted(symbols) for name, symbols in sorted(hyperedges.items())}
