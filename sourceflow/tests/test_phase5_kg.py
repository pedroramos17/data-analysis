"""Phase 5 SQL-backed knowledge graph store tests."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.claims import extract_and_persist_document_claims
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.kg import GraphSchemaError, default_graph_store, node_ref


class Phase5GraphStoreTests(TestCase):
    def setUp(self) -> None:
        self.store = default_graph_store()

    def test_add_edge_persists_confidence_provenance_and_timestamp(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")

        edge = self.store.add_edge(
            node_ref("document", document.pk),
            node_ref("source", document.source_id),
            "published_by",
            confidence=Decimal("0.90"),
            provenance={"created_by": "test"},
            source_document=document,
        )

        self.assertEqual(models.KnowledgeEdge.objects.count(), 1)
        self.assertEqual(edge.edge_type, "published_by")
        self.assertEqual(edge.confidence, Decimal("0.90"))
        self.assertEqual(edge.provenance_json["created_by"], "test")
        self.assertEqual(edge.source_document, document)
        self.assertIsNotNone(edge.observed_at)

    def test_add_edge_rejects_unknown_edge_type_and_bad_endpoints(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        doc_node = node_ref("document", document.pk)
        source_node = node_ref("source", document.source_id)

        with self.assertRaises(GraphSchemaError):
            self.store.add_edge(
                doc_node,
                source_node,
                "teleports_to",
                confidence=Decimal("0.90"),
                provenance={"created_by": "test"},
            )
        with self.assertRaises(GraphSchemaError):
            self.store.add_edge(
                source_node,
                doc_node,
                "published_by",
                confidence=Decimal("0.90"),
                provenance={"created_by": "test"},
            )
        self.assertEqual(models.KnowledgeEdge.objects.count(), 0)

    def test_add_edge_rejects_empty_provenance(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")

        with self.assertRaises(GraphSchemaError):
            self.store.add_edge(
                node_ref("document", document.pk),
                node_ref("source", document.source_id),
                "published_by",
                confidence=Decimal("0.90"),
                provenance={},
            )

    def test_add_edge_is_idempotent_and_updates_confidence(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        doc_node = node_ref("document", document.pk)
        source_node = node_ref("source", document.source_id)

        first = self.store.add_edge(
            doc_node,
            source_node,
            "published_by",
            confidence=Decimal("0.50"),
            provenance={"created_by": "test"},
        )
        second = self.store.add_edge(
            doc_node,
            source_node,
            "published_by",
            confidence=Decimal("0.80"),
            provenance={"created_by": "test", "revised": True},
        )

        self.assertEqual(models.KnowledgeEdge.objects.count(), 1)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.confidence, Decimal("0.80"))
        self.assertTrue(second.provenance_json["revised"])

    def test_upsert_claim_maps_claim_to_provenance_carrying_edges(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        claim = extract_and_persist_document_claims(document)[0].claim

        edges = self.store.upsert_claim(claim)

        edge_types = {edge.edge_type for edge in edges}
        self.assertEqual(edge_types, {"about_subject", "extracted_from", "reported_by", "supported_by"})
        for edge in edges:
            self.assertEqual(edge.source_node_type, "claim")
            self.assertEqual(edge.source_node_id, str(claim.pk))
            self.assertEqual(edge.source_document, document)
            self.assertEqual(edge.evidence_span_id, claim.evidence_span_id)
            self.assertEqual(edge.provenance_json["record_type"], "claim")
            self.assertEqual(edge.provenance_json["record_id"], claim.pk)

    def test_upsert_event_maps_event_to_provenance_carrying_edges(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        event = extract_and_persist_document_events(document)[0].event

        edges = self.store.upsert_event(event)

        edge_types = {edge.edge_type for edge in edges}
        self.assertEqual(edge_types, {"has_actor", "extracted_from", "reported_by", "supported_by"})
        for edge in edges:
            self.assertEqual(edge.source_node_type, "event")
            self.assertEqual(edge.evidence_span_id, event.evidence_span_id)
            self.assertEqual(edge.provenance_json["record_type"], "event")

    def test_upsert_claim_twice_does_not_duplicate_edges(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        claim = extract_and_persist_document_claims(document)[0].claim

        self.store.upsert_claim(claim)
        self.store.upsert_claim(claim)

        self.assertEqual(models.KnowledgeEdge.objects.count(), 4)

    def test_get_neighbors_returns_out_in_and_both_directions(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        claim = extract_and_persist_document_claims(document)[0].claim
        self.store.upsert_claim(claim)
        claim_node = node_ref("claim", claim.pk)
        entity_node = node_ref("entity", claim.subject_entity_id)

        out_neighbors = self.store.get_neighbors(claim_node, direction="out")
        in_neighbors = self.store.get_neighbors(entity_node, direction="in")
        subject_edges = self.store.get_neighbors(claim_node, edge_type="about_subject")

        self.assertEqual(len(out_neighbors), 4)
        self.assertEqual([neighbor.node for neighbor in in_neighbors], [claim_node])
        self.assertEqual([neighbor.node for neighbor in subject_edges], [entity_node])

    def test_find_paths_traverses_multi_hop_provenance(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        claim = extract_and_persist_document_claims(document)[0].claim
        self.store.upsert_claim(claim)
        self.store.add_edge(
            node_ref("document", document.pk),
            node_ref("source", document.source_id),
            "published_by",
            confidence=Decimal("1.00"),
            provenance={"created_by": "test"},
        )

        paths = self.store.find_paths(
            node_ref("claim", claim.pk),
            node_ref("source", document.source_id),
            max_depth=2,
        )

        path_shapes = sorted(tuple(edge.edge_type for edge in path) for path in paths)
        self.assertIn(("reported_by",), path_shapes)
        self.assertIn(("extracted_from", "published_by"), path_shapes)

    def test_query_filters_by_edge_type_and_confidence(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        claim = extract_and_persist_document_claims(document)[0].claim
        self.store.upsert_claim(claim)

        reported = self.store.query(edge_type="reported_by")
        confident = self.store.query(min_confidence=Decimal("0.99"))

        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0].target_node_type, "source")
        self.assertEqual(confident, [])

    def _source(self) -> models.Source:
        source, _created = models.Source.objects.get_or_create(
            name="Example News",
            defaults={
                "url": "https://example.test/feed.xml",
                "source_type": models.Source.SourceType.RSS,
                "language": "en",
            },
        )
        return source

    def _document(self, text: str) -> models.Document:
        source = self._source()
        result = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url=f"https://example.test/phase5-{models.Document.objects.count()}",
                title="Phase 5 knowledge graph",
                raw_text=text,
                published_at=timezone.now(),
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        )
        return result.document
