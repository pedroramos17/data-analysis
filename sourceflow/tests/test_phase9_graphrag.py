"""Phase 9 hybrid GraphRAG retrieval tests."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.claims import ClaimCandidate, persist_claim_candidates
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.graphrag import EvidencePackError, HybridGraphRAGRetriever
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.kg import default_graph_store
from sourceflow.reasoning.contradictions import detect_claim_contradictions


class Phase9GraphRAGTests(TestCase):
    def setUp(self) -> None:
        self.entity = create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        self.source = self._source("Wire A")
        self.counter_source = self._source("Counter B")

    def test_hybrid_retrieval_returns_evidence_pack_with_provenance_and_contradictions(self) -> None:
        document = self._document(self.source, "Petrobras lawsuit risk", "Petrobras faces a lawsuit risk after court filing.")
        counter_document = self._document(self.counter_source, "Petrobras lawsuit denial", "Petrobras faces a lawsuit risk after court filing.")
        event = extract_and_persist_document_events(document)[0].event
        claim = self._claim(document, polarity="negative", object_literal="lawsuit risk", predicate="faces")
        counterclaim = self._claim(counter_document, polarity="positive", object_literal="lawsuit risk", predicate="faces")
        detect_claim_contradictions([claim, counterclaim])
        store = default_graph_store()
        store.upsert_claim(claim)
        store.upsert_claim(counterclaim)
        store.upsert_event(event)

        pack = HybridGraphRAGRetriever().retrieve("What is the Petrobras lawsuit risk?", persist_trace=True)

        self.assertTrue(pack.text_chunks)
        self.assertTrue(pack.supporting_claims)
        self.assertTrue(pack.contradicting_claims)
        self.assertTrue(pack.events)
        self.assertTrue(pack.entities)
        self.assertTrue(pack.graph_paths)
        self.assertTrue(pack.citations)
        self.assertIn("PartialCWA", pack.assumptions_used)
        self.assertEqual(models.RetrievalTrace.objects.count(), 1)
        chunk = pack.text_chunks[0]
        self.assertIn("document_id", chunk.provenance)
        self.assertIn("evidence_span_id", pack.supporting_claims[0].provenance)
        self.assertEqual(pack.contradicting_claims[0].metadata["status"], models.Claim.Status.DISPUTED)

    def test_proof_carrying_answer_includes_required_fields(self) -> None:
        document = self._document(self.source, "Petrobras lawsuit risk", "Petrobras faces a lawsuit risk after court filing.")
        event = extract_and_persist_document_events(document)[0].event
        claim = self._claim(document, polarity="negative", object_literal="lawsuit risk", predicate="faces")
        default_graph_store().upsert_claim(claim)
        default_graph_store().upsert_event(event)

        answer = HybridGraphRAGRetriever().answer_query(
            "Explain Petrobras lawsuit risk",
            "Petrobras has lawsuit-related risk according to retrieved evidence.",
        )

        self.assertEqual(
            set(answer),
            {
                "answer",
                "supporting_claims",
                "contradicting_claims",
                "events",
                "entities",
                "graph_paths",
                "assumptions_used",
                "confidence",
                "confidence_breakdown",
                "what_would_change_this",
                "citations",
            },
        )
        self.assertTrue(answer["supporting_claims"])
        self.assertTrue(answer["events"])
        self.assertTrue(answer["entities"])
        self.assertIn("retrieval_confidence", answer["confidence_breakdown"])
        self.assertIn("extraction_confidence", answer["confidence_breakdown"])
        self.assertIn("reasoning_confidence", answer["confidence_breakdown"])

    def test_no_answer_is_returned_without_evidence(self) -> None:
        with self.assertRaises(EvidencePackError):
            HybridGraphRAGRetriever().answer_query("unknown topic", "Unsupported answer")

    def _source(self, name: str) -> models.Source:
        return models.Source.objects.create(
            name=name,
            url=f"https://example.test/{name.lower().replace(' ', '-')}.xml",
            source_type=models.Source.SourceType.RSS,
            country="BR",
            language="en",
            reliability_score="0.80",
            bias_tags=["business"],
        )

    def _document(self, source: models.Source, title: str, text: str) -> models.Document:
        result = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url=f"https://example.test/phase9-{models.Document.objects.count()}",
                title=title,
                raw_text=text,
                published_at=timezone.now(),
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        )
        return result.document

    def _claim(
        self,
        document: models.Document,
        *,
        polarity: str,
        object_literal: str,
        predicate: str,
    ) -> models.Claim:
        return persist_claim_candidates(
            document,
            [
                ClaimCandidate(
                    subject_text="Petrobras",
                    predicate=predicate,
                    object_text=object_literal,
                    object_literal=object_literal,
                    polarity=polarity,
                    confidence=Decimal("0.80"),
                    evidence_text=document.clean_text or document.raw_text,
                )
            ],
        )[0].claim
