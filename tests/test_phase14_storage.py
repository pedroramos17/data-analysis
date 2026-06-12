"""Phase 14 storage and performance tests.

Covers the Task 14.1 acceptance criteria: snapshots are reproducible, analytics
queries are decoupled from the transactional store (so they cannot block
ingestion), and large document/chunk tables are queried efficiently via DuckDB
over Parquet. Also exercises the local vector store and the optional RDF export.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.claims import extract_and_persist_document_claims
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.kg import default_graph_store
from sourceflow.storage import (
    LocalVectorStore,
    MissingGraphBackend,
    MissingVectorBackend,
    Neo4jGraphAdapter,
    SourceflowAnalytics,
    build_chunk_vectors,
    embed_text,
    export_graph_ntriples,
    snapshot_canonical,
    vector_store,
)

try:
    import duckdb  # noqa: F401
    import pyarrow  # noqa: F401

    _STORAGE_DEPS = True
except ImportError:  # pragma: no cover
    _STORAGE_DEPS = False


@unittest.skipUnless(_STORAGE_DEPS, "duckdb/pyarrow required for storage tests")
class Phase14StorageTests(TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.source = models.Source.objects.create(
            name="Wire A",
            url="https://example.test/wire-a.xml",
            source_type=models.Source.SourceType.RSS,
            language="en",
            reliability_score=Decimal("0.90"),
        )
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        self.document = persist_normalized_document(
            DocumentInput(
                source_id=self.source.pk,
                url="https://example.test/probe",
                title="Petrobras probe",
                raw_text="Petrobras faces a regulatory investigation.",
                published_at=timezone.now(),
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        ).document
        self.claim = extract_and_persist_document_claims(self.document)[0].claim
        self.event = extract_and_persist_document_events(self.document)[0].event
        default_graph_store().upsert_claim(self.claim)

    # -- snapshots ----------------------------------------------------------

    def test_snapshot_writes_parquet_and_is_reproducible(self) -> None:
        first = snapshot_canonical(self.tmp / "snap1")
        second = snapshot_canonical(self.tmp / "snap2")

        self.assertTrue((self.tmp / "snap1" / "documents.parquet").exists())
        self.assertTrue((self.tmp / "snap1" / "manifest.json").exists())
        self.assertGreaterEqual(first.tables["claims"].row_count, 1)
        # Same database state -> identical per-table logical content hashes.
        self.assertEqual(first.content_hashes, second.content_hashes)

    def test_snapshot_changes_when_data_changes(self) -> None:
        before = snapshot_canonical(self.tmp / "before").content_hashes
        create_or_update_entity(canonical_name="Vale", entity_type="Company")
        after = snapshot_canonical(self.tmp / "after").content_hashes
        self.assertNotEqual(before["entities"], after["entities"])

    # -- analytics decoupled from the transactional DB ---------------------

    def test_analytics_run_over_snapshot_not_live_db(self) -> None:
        snapshot_canonical(self.tmp / "snap")
        # Delete from the transactional DB AFTER snapshotting. If analytics read
        # the live DB they'd see zero; reading the snapshot they still see data,
        # which is exactly the "analytics do not block ingestion" decoupling.
        models.Event.objects.all().delete()
        models.Claim.objects.all().delete()

        with SourceflowAnalytics(self.tmp / "snap") as analytics:
            self.assertEqual(analytics.count("events"), 1)
            by_type = analytics.events_by_type()
            self.assertTrue(by_type)
            self.assertEqual(by_type[0]["event_type"], self.event.event_type)
            by_source = analytics.claims_by_source()
            self.assertEqual(by_source[0]["source"], "Wire A")

    def test_analytics_aggregates_large_chunk_table(self) -> None:
        # Many chunks via small chunk size -> exercises the columnar aggregate path.
        big = persist_normalized_document(
            DocumentInput(
                source_id=self.source.pk,
                url="https://example.test/long",
                title="long doc",
                raw_text=" ".join(f"Sentence number {i} about markets." for i in range(60)),
                published_at=timezone.now(),
            ),
            max_chunk_chars=40,
            chunk_overlap=0,
        )
        self.assertGreaterEqual(len(big.chunks), 10)
        snapshot_canonical(self.tmp / "snap")
        with SourceflowAnalytics(self.tmp / "snap") as analytics:
            stats = analytics.chunk_stats()
            self.assertEqual(stats["chunks"], models.DocumentChunk.objects.count())
            self.assertGreater(stats["tokens"], 0)

    # -- vectors ------------------------------------------------------------

    def test_embed_text_is_deterministic(self) -> None:
        self.assertEqual(embed_text("Petrobras regulatory probe"), embed_text("Petrobras regulatory probe"))

    def test_local_vector_store_search_and_roundtrip(self) -> None:
        store = build_chunk_vectors(dim=64)
        self.assertGreaterEqual(len(store), 1)
        results = store.search(embed_text("regulatory investigation", dim=64), k=1)
        self.assertTrue(results)
        self.assertTrue(results[0][0].startswith("chunk:"))

        saved = store.save(self.tmp / "vectors")
        reloaded = LocalVectorStore.load(saved)
        self.assertEqual(len(reloaded), len(store))

    def test_vector_store_factory_optional_backends(self) -> None:
        self.assertIsInstance(vector_store("local", dim=32), LocalVectorStore)
        with self.assertRaises(MissingVectorBackend):
            vector_store("faiss")

    # -- graph export -------------------------------------------------------

    def test_rdf_ntriples_export(self) -> None:
        path = export_graph_ntriples(self.tmp / "graph.nt")
        text = path.read_text(encoding="utf-8")
        self.assertIn("urn:sourceflow:claim:", text)
        self.assertIn("<urn:sourceflow:edge:", text)
        # Reproducible: re-exporting the same graph yields identical content.
        self.assertEqual(text, export_graph_ntriples(self.tmp / "graph2.nt").read_text(encoding="utf-8"))

    def test_neo4j_adapter_requires_driver(self) -> None:
        with self.assertRaises(MissingGraphBackend):
            Neo4jGraphAdapter("bolt://localhost:7687")
