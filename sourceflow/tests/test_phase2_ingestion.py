"""Phase 2 canonical ingestion persistence tests."""

from __future__ import annotations

from django.test import TestCase

from sourceflow import models
from sourceflow.ingestion.evidence import (
    create_evidence_span_for_document,
    evidence_for_belief,
    evidence_for_claim,
)
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document


class Phase2CanonicalIngestionTests(TestCase):
    def test_persist_normalized_document_creates_document_and_chunks(self) -> None:
        source = self._source()

        result = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url="https://example.test/post?utm_source=x&id=1",
                title="Petrobras News",
                raw_text="Petrobras faces a regulatory investigation. " * 8,
                published_at="2026-01-02T03:04:05Z",
                language="en",
                external_id="post-1",
                provenance_json={"source": "unit-test"},
            ),
            ingestion_version="test.v1",
            max_chunk_chars=80,
            chunk_overlap=10,
        )

        document = models.Document.objects.get(pk=result.document.pk)

        self.assertFalse(result.duplicate.is_duplicate)
        self.assertEqual(document.source, source)
        self.assertEqual(document.url, "https://example.test/post?id=1")
        self.assertTrue(document.content_hash)
        self.assertEqual(document.language, "en")
        self.assertEqual(document.metadata_json["ingestion_version"], "test.v1")
        self.assertGreaterEqual(len(result.chunks), 1)
        for chunk in result.chunks:
            self.assertEqual(chunk.document_id, document.pk)
            self.assertEqual(document.clean_text[chunk.char_start : chunk.char_end], chunk.text)

    def test_duplicate_document_is_detected_by_content_hash_or_url(self) -> None:
        source = self._source()
        payload = DocumentInput(
            source_id=source.pk,
            url="https://example.test/duplicate",
            title="Duplicate",
            raw_text="Same body",
        )

        first = persist_normalized_document(payload)
        second = persist_normalized_document(payload)

        self.assertFalse(first.duplicate.is_duplicate)
        self.assertTrue(second.duplicate.is_duplicate)
        self.assertEqual(first.document.pk, second.document.pk)
        self.assertEqual(models.Document.objects.count(), 1)

    def test_evidence_span_and_explanations_trace_to_document_chunk(self) -> None:
        source = self._source()
        persisted = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url="https://example.test/petrobras-risk",
                title="Petrobras risk",
                raw_text="Petrobras faces a regulatory investigation.",
            ),
            max_chunk_chars=80,
            chunk_overlap=0,
        )
        evidence = create_evidence_span_for_document(
            persisted.document,
            "regulatory investigation",
            extractor_name="unit-test",
            extractor_version="1",
            confidence="0.95",
        )
        entity = models.Entity.objects.create(canonical_name="Petrobras", entity_type="Company")
        regulator = models.Entity.objects.create(canonical_name="Regulator", entity_type="Regulator")
        claim = models.Claim.objects.create(
            subject_entity=entity,
            predicate="faces",
            object_entity=regulator,
            object_literal="regulatory investigation",
            polarity=models.Claim.Polarity.NEGATIVE,
            modality=models.Claim.Modality.ASSERTED,
            confidence="0.90",
            source=source,
            document=persisted.document,
            evidence_span=evidence,
        )
        policy = models.AssumptionPolicy.objects.create(
            code=models.AssumptionPolicy.PolicyCode.OWA,
            name="Open world",
        )
        belief = models.Belief.objects.create(
            belief_type="risk",
            subject_entity=entity,
            predicate="increases",
            object_literal="regulatory_risk",
            truth_status=models.Belief.TruthStatus.TRUE_SUPPORTED,
            confidence="0.80",
            assumption_policy=policy,
        )
        models.Justification.objects.create(
            belief=belief,
            support_type=models.Justification.SupportType.SUPPORTS,
            supporting_claim=claim,
            weight="1.000",
        )
        contradiction = models.Claim.objects.create(
            subject_entity=entity,
            predicate="faces",
            object_literal="no regulatory investigation",
            polarity=models.Claim.Polarity.POSITIVE,
            modality=models.Claim.Modality.DENIED,
            confidence="0.40",
            source=source,
            document=persisted.document,
            evidence_span=evidence,
        )
        models.Justification.objects.create(
            belief=belief,
            support_type=models.Justification.SupportType.CONTRADICTS,
            supporting_claim=contradiction,
            weight="0.400",
        )

        claim_payload = evidence_for_claim(claim.pk)
        belief_payload = evidence_for_belief(belief.pk)

        self.assertEqual(claim_payload["document"]["id"], persisted.document.pk)
        self.assertEqual(claim_payload["chunk"]["id"], evidence.chunk_id)
        self.assertEqual(claim_payload["evidence_span"]["text"], "regulatory investigation")
        self.assertEqual(len(belief_payload["supporting_claims"]), 1)
        self.assertEqual(len(belief_payload["contradicting_claims"]), 1)

    def _source(self) -> models.Source:
        return models.Source.objects.create(
            name="Example News",
            url="https://example.test/feed.xml",
            source_type=models.Source.SourceType.RSS,
            language="en",
        )
