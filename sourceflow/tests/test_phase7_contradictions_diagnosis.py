"""Phase 7 contradiction handling and diagnosis persistence tests."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from sourceflow import models
from sourceflow.claims import ClaimCandidate, persist_claim_candidates
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.kg import default_graph_store
from sourceflow.reasoning import InferenceEngine, RuleDefinition
from sourceflow.reasoning.contradictions import DISPUTE_STATUS, detect_claim_contradictions
from sourceflow.reasoning.diagnosis import diagnose_stock_move


class Phase7ContradictionsDiagnosisTests(TestCase):
    def setUp(self) -> None:
        self.entity = create_or_update_entity(canonical_name="Petrobras", entity_type="Company")

    def test_detect_claim_contradictions_preserves_claims_and_creates_edges(self) -> None:
        positive = self._claim("Source A", "positive")
        negative = self._claim("Source B", "negative")

        results = detect_claim_contradictions([positive, negative])

        self.assertEqual(len(results), 1)
        positive.refresh_from_db()
        negative.refresh_from_db()
        self.assertEqual(positive.status, models.Claim.Status.DISPUTED)
        self.assertEqual(negative.status, models.Claim.Status.DISPUTED)
        self.assertEqual(positive.metadata_json["dispute_status"], DISPUTE_STATUS)
        self.assertEqual(negative.metadata_json["dispute_status"], DISPUTE_STATUS)
        self.assertEqual(models.Claim.objects.count(), 2)
        self.assertEqual(models.KnowledgeEdge.objects.filter(edge_type="contradicts").count(), 2)
        explanation = results[0].explanation
        self.assertEqual(explanation["left"]["source_name"], "Source A")
        self.assertEqual(explanation["right"]["source_name"], "Source B")

    def test_disputed_claim_support_does_not_derive_hard_truth(self) -> None:
        positive = self._claim("Source A", "positive")
        negative = self._claim("Source B", "negative")
        detect_claim_contradictions([positive, negative])
        positive.refresh_from_db()
        rule = RuleDefinition.from_mapping(
            {
                "id": "profit_growth_increases_risk_appetite",
                "type": "deductive",
                "when": [{"predicate": "reports"}, {"polarity": "positive"}],
                "then": [{"belief_type": "risk", "predicate": "decreases", "object": "risk_aversion"}],
            }
        )

        results = InferenceEngine([rule]).infer_from_support(positive)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "skipped_contradicted_support")
        self.assertEqual(models.Belief.objects.count(), 0)

    def test_diagnose_stock_move_uses_event_claim_kg_and_market_evidence(self) -> None:
        document = self._document("Example News", "Petrobras faces a lawsuit.")
        event = extract_and_persist_document_events(document)[0].event
        claim = self._claim("Source A", "negative", object_literal="lawsuit", predicate="faces")
        edge = default_graph_store().add_edge(
            default_graph_store().add_node("event", event.pk),
            default_graph_store().add_node("entity", self.entity.pk),
            "affects",
            confidence=Decimal("0.80"),
            provenance={"created_by": "test"},
            source_document=document,
            evidence_span=event.evidence_span,
        )

        hypotheses = diagnose_stock_move(
            subject_entity=self.entity,
            price_move=Decimal("-0.04"),
            events=[event],
            claims=[claim],
            graph_edges=[edge],
            market_evidence={"price_move": "-4%", "volume_spike": "2.4x"},
        )

        self.assertGreaterEqual(hypotheses[0].confidence, hypotheses[1].confidence)
        self.assertTrue(hypotheses[0].supporting_evidence)
        self.assertTrue(hypotheses[0].graph_path)
        self.assertIsNotNone(hypotheses[0].missing_evidence)
        self.assertTrue(hypotheses[0].recommended_next_retrieval)

    def _source(self, name: str) -> models.Source:
        source, _created = models.Source.objects.get_or_create(
            name=name,
            defaults={
                "url": f"https://example.test/{name.lower().replace(' ', '-')}.xml",
                "source_type": models.Source.SourceType.RSS,
                "language": "en",
            },
        )
        return source

    def _document(self, source_name: str, text: str) -> models.Document:
        source = self._source(source_name)
        result = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url=f"https://example.test/phase7-{models.Document.objects.count()}",
                title="Phase 7 reasoning",
                raw_text=text,
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        )
        return result.document

    def _claim(
        self,
        source_name: str,
        polarity: str,
        *,
        object_literal: str = "profit growth",
        predicate: str = "reports",
    ) -> models.Claim:
        document = self._document(source_name, f"Petrobras {predicate} {object_literal}.")
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
                    evidence_text=f"Petrobras {predicate} {object_literal}.",
                )
            ],
        )[0].claim
