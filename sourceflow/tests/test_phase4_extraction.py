"""Phase 4 canonical claim and event extraction tests."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.claims import ClaimCandidate, extract_and_persist_document_claims, persist_claim_candidates
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.ingestion.evidence import evidence_for_claim
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document


class Phase4CanonicalExtractionTests(TestCase):
    def test_extract_and_persist_document_claims_creates_structured_claims(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        entity = create_or_update_entity(canonical_name="Petrobras", entity_type="Company")

        results = extract_and_persist_document_claims(document)

        self.assertEqual(len(results), 1)
        claim = results[0].claim
        self.assertIsNotNone(claim)
        self.assertEqual(claim.subject_entity, entity)
        self.assertEqual(claim.predicate, "faces")
        self.assertEqual(claim.object_literal, "a regulatory investigation")
        self.assertEqual(claim.polarity, models.Claim.Polarity.NEGATIVE)
        self.assertEqual(claim.modality, models.Claim.Modality.ASSERTED)
        self.assertEqual(claim.status, models.Claim.Status.ACTIVE)
        self.assertEqual(claim.source_id, document.source_id)
        self.assertEqual(claim.document, document)
        self.assertIsNotNone(claim.evidence_span_id)
        self.assertIn("Petrobras faces", claim.evidence_span.text)

    def test_claim_evidence_payload_traces_to_source_document_and_chunk(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        claim = extract_and_persist_document_claims(document)[0].claim

        payload = evidence_for_claim(claim.pk)

        self.assertEqual(payload["source"]["id"], document.source_id)
        self.assertEqual(payload["document"]["id"], document.pk)
        self.assertIsNotNone(payload["chunk"])
        self.assertEqual(payload["evidence_span"]["id"], claim.evidence_span_id)

    def test_invalid_claim_candidate_is_rejected_by_default(self) -> None:
        document = self._document("No usable claim here.")

        results = persist_claim_candidates(
            document,
            [
                ClaimCandidate(
                    subject_text="",
                    predicate="faces",
                    object_literal="regulatory investigation",
                    evidence_text="",
                )
            ],
        )

        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0].claim)
        self.assertFalse(results[0].validation.is_valid)
        self.assertEqual(models.Claim.objects.count(), 0)

    def test_extract_and_persist_document_events_creates_market_events(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        entity = create_or_update_entity(canonical_name="Petrobras", entity_type="Company")

        results = extract_and_persist_document_events(document)

        self.assertEqual(len(results), 1)
        event = results[0].event
        self.assertEqual(event.actor_entity, entity)
        self.assertEqual(event.predicate, "faces")
        self.assertEqual(event.event_type, models.Event.EventType.REGULATORY_ACTION)
        self.assertEqual(event.polarity, models.Claim.Polarity.NEGATIVE)
        self.assertEqual(event.source_id, document.source_id)
        self.assertEqual(event.document, document)
        self.assertIsNotNone(event.evidence_span_id)
        self.assertIsNotNone(event.extraction_time)
        self.assertIsNotNone(event.event_time)
        self.assertNotEqual(event.extraction_time, event.event_time)
        self.assertIn("regulatory_risk", event.metadata_json["risk_channels"])

    def test_unknown_event_actor_creates_nil_entity_instead_of_dropping_event(self) -> None:
        document = self._document("UnknownCo faces a regulatory investigation.")

        result = extract_and_persist_document_events(document)[0]

        self.assertEqual(result.event.actor_entity.canonical_name, "UnknownCo")
        self.assertTrue(result.event.actor_entity.metadata_json["nil_candidate"])

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
                url=f"https://example.test/phase4-{models.Document.objects.count()}",
                title="Phase 4 extraction",
                raw_text=text,
                published_at=timezone.now(),
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        )
        return result.document
