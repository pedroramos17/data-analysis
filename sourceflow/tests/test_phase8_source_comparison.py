"""Phase 8 provider grouping and source-comparison tests."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.analysis import group_sources, source_reliability_metadata, update_source_reliability_metadata
from sourceflow.claims import ClaimCandidate, compare_event_cluster_claims, persist_claim_candidates
from sourceflow.entities import create_or_update_entity
from sourceflow.events import cluster_events, extract_and_persist_document_events
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document


class Phase8SourceComparisonTests(TestCase):
    def setUp(self) -> None:
        self.entity = create_or_update_entity(canonical_name="Petrobras", entity_type="Company")
        self.wire_owner = models.ProviderOwner.objects.create(name="Wire Co", canonical_name="Wire Co")
        self.regional_owner = models.ProviderOwner.objects.create(name="Regional Co", canonical_name="Regional Co")

    def test_sources_group_by_owner_and_reliability_metadata_updates(self) -> None:
        wire_a = self._source("Wire A", self.wire_owner, reliability="0.80")
        wire_b = self._source("Wire B", self.wire_owner, reliability="0.60")
        regional = self._source("Regional", self.regional_owner, reliability="0.90")

        metadata = update_source_reliability_metadata(
            wire_a,
            reliability_score="0.75",
            bias_tags=["Business", "Market"],
            country="BR",
            source_type=models.Source.SourceType.HTML,
        )
        groups = group_sources([wire_a, wire_b, regional], by=("owner",))

        wire_a.refresh_from_db()
        self.assertEqual(metadata.reliability_score, Decimal("0.75"))
        self.assertEqual(source_reliability_metadata(wire_a).bias_tags, ("business", "market"))
        self.assertEqual(len(groups), 2)
        wire_group = next(group for group in groups if group.key.owner == "wire_co")
        self.assertEqual(set(wire_group.source_names), {"Wire A", "Wire B"})

    def test_event_cluster_comparison_reports_owner_omission_under_partial_cwa(self) -> None:
        wire_source = self._source("Wire A", self.wire_owner, reliability="0.80")
        regional_source = self._source("Regional", self.regional_owner, reliability="0.70")
        wire_doc = self._document(wire_source, "Wire: Petrobras lawsuit risk", "Petrobras faces a lawsuit.")
        regional_doc = self._document(regional_source, "Regional: Petrobras update", "Petrobras faces a lawsuit.")
        wire_event = extract_and_persist_document_events(wire_doc)[0].event
        regional_event = extract_and_persist_document_events(regional_doc)[0].event
        wire_claim = self._claim(wire_doc, polarity="negative", object_literal="lawsuit", predicate="faces")
        clusters = cluster_events([wire_event, regional_event], claims=[wire_claim])

        comparison = compare_event_cluster_claims(
            clusters[0],
            expected_sources=[wire_source, regional_source],
            group_by=("owner",),
        )

        self.assertEqual(comparison.assumption_policy, "PartialCWA")
        self.assertEqual(len(comparison.summaries), 2)
        regional_summary = next(summary for summary in comparison.summaries if summary.group_key.owner == "regional_co")
        self.assertEqual(regional_summary.claim_count, 0)
        self.assertTrue(regional_summary.omitted_claims)
        omissions = comparison.omissions
        self.assertEqual(len(omissions), 1)
        self.assertIn("source omitted", omissions[0].description)
        self.assertFalse(omissions[0].inferred_false)
        self.assertEqual(omissions[0].assumption_policy, "PartialCWA")

    def test_source_comparison_detects_claim_repetition_and_sentiment_shift(self) -> None:
        wire_source = self._source("Wire A", self.wire_owner, reliability="0.80")
        regional_source = self._source("Regional", self.regional_owner, reliability="0.70")
        wire_doc_1 = self._document(wire_source, "Wire lawsuit warning", "Petrobras faces a lawsuit.")
        wire_doc_2 = self._document(wire_source, "Wire litigation pressure", "Petrobras faces a lawsuit.")
        regional_doc = self._document(regional_source, "Regional neutral update", "Petrobras faces a lawsuit.")
        events = [
            extract_and_persist_document_events(wire_doc_1)[0].event,
            extract_and_persist_document_events(wire_doc_2)[0].event,
            extract_and_persist_document_events(regional_doc)[0].event,
        ]
        claims = [
            self._claim(wire_doc_1, polarity="negative", object_literal="lawsuit", predicate="faces"),
            self._claim(wire_doc_2, polarity="negative", object_literal="lawsuit", predicate="faces"),
            self._claim(regional_doc, polarity="positive", object_literal="lawsuit", predicate="faces"),
        ]
        cluster = cluster_events(events, claims=claims)[0]

        comparison = compare_event_cluster_claims(cluster, group_by=("owner",))

        detection_types = {finding.detection_type for finding in comparison.findings}
        self.assertIn("claim_repetition", detection_types)
        self.assertIn("sentiment_shift", detection_types)
        self.assertIn("missing_counterclaim", detection_types)

    def _source(self, name: str, owner: models.ProviderOwner, *, reliability: str) -> models.Source:
        return models.Source.objects.create(
            name=name,
            url=f"https://example.test/{name.lower().replace(' ', '-')}.xml",
            provider_owner=owner,
            source_type=models.Source.SourceType.RSS,
            country="BR",
            language="en",
            reliability_score=reliability,
            bias_tags=["business"],
        )

    def _document(self, source: models.Source, title: str, text: str) -> models.Document:
        result = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url=f"https://example.test/phase8-{models.Document.objects.count()}",
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
