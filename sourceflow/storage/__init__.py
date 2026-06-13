"""Sourceflow performance and storage boundary (Phase 14).

Transactional state stays in the Django ORM (SQLite/Postgres). This package adds
the analytical and historical storage strategy: reproducible Parquet snapshots,
DuckDB analytics decoupled from ingestion, a local-first embedding store with
optional FAISS/Chroma backends, and an optional RDF/Neo4j graph export over the
SQL-backed knowledge graph.
"""

from sourceflow.storage.analytics import AnalyticsError, SourceflowAnalytics
from sourceflow.storage.graph_export import (
    MissingGraphBackend,
    Neo4jGraphAdapter,
    edge_to_triples,
    export_graph_ntriples,
    to_ntriples,
)
from sourceflow.storage.snapshot import (
    SNAPSHOT_TABLES,
    SnapshotManifest,
    TableSnapshot,
    snapshot_canonical,
)
from sourceflow.storage.vectors import (
    LocalVectorStore,
    MissingVectorBackend,
    VectorStore,
    build_chunk_vectors,
    embed_text,
    vector_store,
)

__all__ = [
    "SNAPSHOT_TABLES",
    "AnalyticsError",
    "LocalVectorStore",
    "MissingGraphBackend",
    "MissingVectorBackend",
    "Neo4jGraphAdapter",
    "SnapshotManifest",
    "SourceflowAnalytics",
    "TableSnapshot",
    "VectorStore",
    "build_chunk_vectors",
    "edge_to_triples",
    "embed_text",
    "export_graph_ntriples",
    "snapshot_canonical",
    "to_ntriples",
    "vector_store",
]
