"""Light graph features from correlations."""

from monitoring.compute.array_api import (
    as_float_array,
    free_device_cache,
    safe_corrcoef,
)


def compute_graph_features(
    values: object,
    top_k: int = 3,
    backend: str = "auto",
    profile: str = "local_cpu_low",
    batch_size: int = 64,
    precision: str = "float32",
    max_vram_gb: float | None = None,
    partition: str = "",
) -> dict[str, object]:
    """Compute correlation graph, top-k edges, degree, and PageRank.

    Example:
        `features = compute_graph_features([[1, 2], [2, 4], [3, 6]])`
    """
    matrix = as_float_array(values, precision)
    correlations = safe_corrcoef(matrix)
    edges = _topk_edges(correlations, top_k)
    weighted_degree = _weighted_degree(correlations)
    pagerank = _pagerank(correlations)
    if profile == "local_mx350_queue":
        free_device_cache(backend)
    return _payload(
        correlations, edges, weighted_degree, pagerank, backend, profile,
        batch_size, max_vram_gb, partition
    )


def _topk_edges(correlations: object, top_k: int) -> list[dict[str, object]]:
    np = _numpy_module()
    edges: list[dict[str, object]] = []
    for source_index in range(correlations.shape[0]):
        row = np.abs(correlations[source_index]).copy()
        row[source_index] = -1
        targets = np.argsort(row)[-top_k:][::-1]
        edges.extend(
            _edge(source_index, int(target), correlations) for target in targets
        )
    return edges


def _edge(
    source_index: int, target_index: int, correlations: object
) -> dict[str, object]:
    return {
        "source": source_index,
        "target": target_index,
        "weight": float(correlations[source_index, target_index]),
    }


def _weighted_degree(correlations: object) -> object:
    np = _numpy_module()
    matrix = np.abs(correlations).copy()
    np.fill_diagonal(matrix, 0.0)
    return matrix.sum(axis=1)


def _pagerank(correlations: object, iterations: int = 20) -> object:
    np = _numpy_module()
    weights = np.abs(correlations).copy()
    np.fill_diagonal(weights, 0.0)
    transition = _row_normalized(weights)
    scores = np.ones(weights.shape[0], dtype=float) / weights.shape[0]
    for _index in range(iterations):
        scores = 0.15 / weights.shape[0] + 0.85 * transition.T.dot(scores)
    return scores


def _row_normalized(weights: object) -> object:
    np = _numpy_module()
    totals = weights.sum(axis=1, keepdims=True)
    return weights / np.where(totals == 0, 1.0, totals)


def _payload(
    correlations: object,
    edges: list[dict[str, object]],
    weighted_degree: object,
    pagerank: object,
    backend: str,
    profile: str,
    batch_size: int,
    max_vram_gb: float | None,
    partition: str,
) -> dict[str, object]:
    return {
        "correlation": correlations,
        "edges": edges,
        "weighted_degree": weighted_degree,
        "pagerank": pagerank,
        "backend": backend,
        "profile": profile,
        "batch_size": batch_size,
        "max_vram_gb": max_vram_gb,
        "partition": partition,
    }


def _numpy_module() -> object:
    try:
        import numpy
    except ImportError as error:
        message = "Graph features require numpy; expected installed package"
        raise RuntimeError(message) from error
    return numpy
