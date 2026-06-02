"""Graph sampling and snapshot artifact persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from quant4.services.graphs.graph_builders import GraphBuildResult, GraphEdge
from quant4.services.registry import stable_config_hash
from quant4.services.run_metadata import DateRange, build_run_metadata_fields


def persist_graph_snapshot(
    name: str,
    result: GraphBuildResult,
    output_dir: str,
    data_range: DateRange,
    split_range: DateRange,
    random_seed: int = 0,
    provenance: Mapping[str, object] | None = None,
) -> object:
    """Write graph artifacts and persist a shared Quant4 GraphSnapshot.

    Example:
        `persist_graph_snapshot("g", result, "data/graphs", dr, sr)`
    """
    from quant4.models import GraphSnapshot

    paths = _write_graph_artifacts(name, result, output_dir)
    config = _snapshot_config(result)
    return GraphSnapshot.objects.create(
        name=name,
        component_name="quant4_graph_lab",
        config_json=config,
        config_hash=stable_config_hash(config),
        node_count=len(result.nodes),
        edge_count=len(result.edges),
        artifact_uri=str(Path(output_dir)),
        node_path=paths["node_path"],
        edge_path=paths["edge_path"],
        adjacency_path=paths["adjacency_path"],
        feature_schema_json=_feature_schema(result),
        metrics_json=_metrics(result, paths),
        status="RESEARCH_ONLY",
        **build_run_metadata_fields(data_range, split_range, random_seed, provenance),
    )


def sample_top_edges(
    edges: Sequence[GraphEdge],
    limit: int,
) -> list[GraphEdge]:
    """Return strongest graph edges for lightweight downstream use.

    Example:
        `sample_top_edges(edges, 10)`
    """
    return sorted(edges, key=_abs_weight, reverse=True)[: max(0, limit)]


def _write_graph_artifacts(
    name: str,
    result: GraphBuildResult,
    output_dir: str,
) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = _artifact_paths(root, name)
    _write_json(paths["node_path"], {"nodes": result.nodes})
    _write_json(paths["edge_path"], {"edges": result.edges})
    _write_json(paths["adjacency_path"], {"adjacency": result.adjacency})
    return paths


def _artifact_paths(root: Path, name: str) -> dict[str, str]:
    safe_name = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in name
    )
    return {
        "node_path": str(root / f"{safe_name}_nodes.json"),
        "edge_path": str(root / f"{safe_name}_edges.json"),
        "adjacency_path": str(root / f"{safe_name}_adjacency.json"),
    }


def _write_json(path: str, payload: Mapping[str, object]) -> None:
    Path(path).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _snapshot_config(result: GraphBuildResult) -> dict[str, object]:
    return {
        "engine": "quant4_graph_lab",
        "builder": str(result.metadata.get("builder", "")),
    }


def _feature_schema(result: GraphBuildResult) -> dict[str, object]:
    return {
        "nodes": "symbol",
        "edges": ["source", "target", "weight", "relation_type"],
        "fit_scope": "window_end_past_only",
        "builder": str(result.metadata.get("builder", "")),
    }


def _metrics(
    result: GraphBuildResult,
    paths: Mapping[str, str],
) -> dict[str, object]:
    return dict(result.metadata) | {
        "artifact_paths": dict(paths),
        "validation_prior_note": (
            "MST/PMFG filters are priors, not learned graph replacements"
        ),
    }


def _abs_weight(edge: GraphEdge) -> float:
    return abs(float(edge["weight"]))
