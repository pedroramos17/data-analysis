"""Graph filtering priors for Quant4 graph validation."""

from __future__ import annotations

from collections.abc import Sequence

from quant4.services.graphs.graph_builders import GraphEdge
from quant4.services.registry import OptionalDependencyMissingError


class MSTFilter:
    """Build a maximum spanning tree validation prior."""

    def filter_edges(self, edges: Sequence[GraphEdge]) -> list[GraphEdge]:
        """Return tree edges without claiming learned graph replacement."""
        tree: list[GraphEdge] = []
        groups: dict[str, str] = {}
        for edge in sorted(edges, key=_abs_weight, reverse=True):
            if _find(groups, str(edge["source"])) == _find(groups, str(edge["target"])):
                continue
            tree.append(dict(edge) | {"filter_role": "validation_prior"})
            _union(groups, str(edge["source"]), str(edge["target"]))
        return tree


class PMFGFilter:
    """Optional PMFG filter stub."""

    def filter_edges(self, edges: Sequence[GraphEdge]) -> list[GraphEdge]:
        """Raise a clear optional dependency error for PMFG."""
        raise OptionalDependencyMissingError(
            "Component 'pmfg' requires optional dependency 'quant4_pmfg'; "
            "expected installed module"
        )


class TMFGFilter:
    """Optional TMFG filter stub."""

    def filter_edges(self, edges: Sequence[GraphEdge]) -> list[GraphEdge]:
        """Raise a clear optional dependency error for TMFG."""
        raise OptionalDependencyMissingError(
            "Component 'tmfg' requires optional dependency 'quant4_tmfg'; "
            "expected installed module"
        )


class RandomMatrixFilteredCovariance:
    """Optional random-matrix covariance filter stub."""

    def filter_covariance(
        self,
        covariance: Sequence[Sequence[float]],
    ) -> list[list[float]]:
        """Raise a clear optional dependency error for RMT filters."""
        raise OptionalDependencyMissingError(
            "Component 'random_matrix_filtered_covariance' requires optional "
            "dependency 'quant4_rmt'; expected installed module"
        )


def _abs_weight(edge: GraphEdge) -> float:
    return abs(float(edge["weight"]))


def _find(groups: dict[str, str], node: str) -> str:
    groups.setdefault(node, node)
    while groups[node] != node:
        node = groups[node]
    return node


def _union(groups: dict[str, str], left: str, right: str) -> None:
    groups[_find(groups, right)] = _find(groups, left)
