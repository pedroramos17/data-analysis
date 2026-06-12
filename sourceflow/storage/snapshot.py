"""Reproducible Parquet snapshots of the canonical sourceflow tables.

The transactional state lives in the Django ORM (SQLite/Postgres). For analytics
and historical reproducibility we export curated canonical tables to Parquet,
each with a manifest entry carrying a *logical* content hash -- the SHA-256 of
the ordered, type-normalized rows. Because the hash is over logical content
(not the Parquet bytes, which can carry writer metadata), two snapshots of the
same database state produce identical hashes, which is what "snapshots are
reproducible" means here.

Rows are streamed with ``.iterator()`` so large document/chunk tables export
without materializing the whole table in memory.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

# Curated canonical tables and the stable columns we snapshot for analytics.
# (Heavy free-text columns like raw_text are intentionally excluded; chunk text
# is kept because retrieval/analytics over it is the point.)
SNAPSHOT_TABLES: dict[str, tuple[str, list[str]]] = {
    "sources": ("Source", ["id", "name", "source_type", "provider_owner_id", "country", "language", "reliability_score"]),
    "documents": ("Document", ["id", "source_id", "url", "title", "content_hash", "language", "published_at"]),
    "chunks": ("DocumentChunk", ["id", "document_id", "chunk_index", "char_start", "char_end", "token_count", "content_hash"]),
    "entities": ("Entity", ["id", "canonical_name", "entity_type", "sector", "country", "confidence"]),
    "claims": ("Claim", ["id", "subject_entity_id", "predicate", "object_literal", "polarity", "modality", "confidence", "status", "source_id", "document_id", "evidence_span_id"]),
    "events": ("Event", ["id", "actor_entity_id", "predicate", "event_type", "polarity", "confidence", "source_id", "document_id", "evidence_span_id", "event_time"]),
    "edges": ("KnowledgeEdge", ["id", "edge_type", "source_node_type", "source_node_id", "target_node_type", "target_node_id", "confidence"]),
    "beliefs": ("Belief", ["id", "belief_type", "subject_entity_id", "predicate", "truth_status", "confidence", "status"]),
}


@dataclass(frozen=True)
class TableSnapshot:
    name: str
    parquet_path: str
    row_count: int
    columns: list[str]
    content_hash: str


@dataclass(frozen=True)
class SnapshotManifest:
    snapshot_dir: str
    tables: dict[str, TableSnapshot] = field(default_factory=dict)

    @property
    def content_hashes(self) -> dict[str, str]:
        """The per-table logical hashes -- the reproducibility fingerprint."""
        return {name: table.content_hash for name, table in self.tables.items()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_dir": self.snapshot_dir,
            "tables": {
                name: {
                    "parquet_path": table.parquet_path,
                    "row_count": table.row_count,
                    "columns": table.columns,
                    "content_hash": table.content_hash,
                }
                for name, table in self.tables.items()
            },
        }


def _jsonify(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _logical_hash(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def snapshot_canonical(
    dest_dir: str | Path,
    *,
    tables: dict[str, tuple[str, list[str]]] | None = None,
    batch_size: int = 1000,
) -> SnapshotManifest:
    """Export curated canonical tables to Parquet + a reproducible manifest."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from sourceflow import models

    table_specs = tables or SNAPSHOT_TABLES
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    snapshots: dict[str, TableSnapshot] = {}
    for name, (model_name, columns) in table_specs.items():
        model = getattr(models, model_name)
        rows: list[dict[str, Any]] = []
        # Deterministic order + streaming for large tables.
        for record in model.objects.order_by("pk").values(*columns).iterator(chunk_size=batch_size):
            rows.append({column: _jsonify(record[column]) for column in columns})

        parquet_path = dest / f"{name}.parquet"
        arrow_columns = {column: [row[column] for row in rows] for column in columns}
        pq.write_table(pa.table(arrow_columns) if rows else pa.table({c: [] for c in columns}), parquet_path)

        snapshots[name] = TableSnapshot(
            name=name,
            parquet_path=str(parquet_path),
            row_count=len(rows),
            columns=list(columns),
            content_hash=_logical_hash(rows),
        )

    manifest = SnapshotManifest(snapshot_dir=str(dest), tables=snapshots)
    (dest / "manifest.json").write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return manifest
