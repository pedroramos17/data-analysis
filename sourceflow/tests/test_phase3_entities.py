"""Phase 3 entity extraction and linking tests."""

from __future__ import annotations

from django.test import TestCase

from sourceflow import models
from sourceflow.entities import (
    EntityLinkContext,
    EntityLinker,
    EntityMentionCandidate,
    create_or_update_entity,
    extract_link_and_persist_document_mentions,
    merge_entities,
    resolve_entity_candidate,
    upsert_entity_alias,
)
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.reasoning.assumptions import AssumptionPolicyCode


class Phase3EntityLinkingTests(TestCase):
    def test_ticker_and_name_resolution_are_context_aware(self) -> None:
        meta = create_or_update_entity(
            canonical_name="Meta Platforms",
            entity_type="Company",
            external_ids_json={"ticker": {"value": "META", "namespace": "NASDAQ"}},
            aliases=[{"alias": "Facebook"}, {"alias": "Meta"}],
        )
        materials = create_or_update_entity(
            canonical_name="Meta Materials",
            entity_type="Company",
            external_ids_json={"ticker": {"value": "META", "namespace": "CSE"}},
        )

        nasdaq_resolution = resolve_entity_candidate(
            EntityMentionCandidate("META", "Security", 0, 4),
            EntityLinkContext(exchange="NASDAQ"),
        )
        cse_resolution = resolve_entity_candidate(
            EntityMentionCandidate("META", "Security", 0, 4),
            EntityLinkContext(exchange="CSE"),
        )
        name_resolution = resolve_entity_candidate(EntityMentionCandidate("Facebook", "Company", 0, 8))

        self.assertEqual(nasdaq_resolution.entity, meta)
        self.assertEqual(nasdaq_resolution.assumption_policy, AssumptionPolicyCode.UNIQUE_NAME)
        self.assertEqual(cse_resolution.entity, materials)
        self.assertEqual(name_resolution.entity, meta)
        self.assertEqual(name_resolution.assumption_policy, AssumptionPolicyCode.NO_UNIQUE_NAME)

    def test_unknown_entity_persists_as_nil_candidate(self) -> None:
        document = self._document("UnknownCo announced a financing round.")
        result = extract_link_and_persist_document_mentions(document)
        nil_mentions = [item.mention for item in result if item.mention.mention_text == "UnknownCo"]

        self.assertEqual(len(nil_mentions), 1)
        self.assertIsNone(nil_mentions[0].entity_id)
        self.assertEqual(nil_mentions[0].status, "nil_candidate")
        self.assertEqual(nil_mentions[0].metadata_json["nil_reason"], "no_canonical_entity_match")

    def test_extract_link_and_persist_document_mentions_links_aliases_with_evidence(self) -> None:
        entity = create_or_update_entity(
            canonical_name="Petrobras",
            entity_type="Company",
            aliases=[{"alias": "Petrobras"}, {"alias": "PETR4", "alias_type": "ticker", "namespace": "B3"}],
        )
        document = self._document("Petrobras shares PETR4 rallied after earnings.")

        result = extract_link_and_persist_document_mentions(
            document,
            context=EntityLinkContext(exchange="B3"),
        )
        linked = [item.mention for item in result if item.mention.entity_id == entity.pk]

        self.assertGreaterEqual(len(linked), 1)
        for mention in linked:
            self.assertEqual(mention.status, "linked")
            self.assertIsNotNone(mention.evidence_span_id)
            self.assertEqual(document.clean_text[mention.char_start : mention.char_end], mention.mention_text)

    def test_fuzzy_company_name_resolution(self) -> None:
        entity = create_or_update_entity(canonical_name="Petrobras", entity_type="Company")

        resolution = EntityLinker().link(EntityMentionCandidate("Petrobras SA", "Company", 0, 12))

        self.assertEqual(resolution.entity, entity)
        self.assertEqual(resolution.strategy, "name_fuzzy")

    def test_merge_entities_remaps_mentions_claims_events_beliefs_and_aliases(self) -> None:
        source = self._source()
        document = self._document("Meta Platforms and Facebook are related.", source=source)
        primary = create_or_update_entity(canonical_name="Meta Platforms", entity_type="Company")
        duplicate = create_or_update_entity(canonical_name="Facebook", entity_type="Company")
        upsert_entity_alias(duplicate, "FB", alias_type="ticker", namespace="NASDAQ")
        persisted = extract_link_and_persist_document_mentions(document)
        duplicate_mentions = [item.mention for item in persisted if item.mention.entity_id == duplicate.pk]
        evidence = document.evidence_spans.first()
        policy = models.AssumptionPolicy.objects.create(
            code=models.AssumptionPolicy.PolicyCode.OWA,
            name="Open world",
        )
        claim = models.Claim.objects.create(
            subject_entity=duplicate,
            predicate="rebranded_as",
            object_entity=primary,
            confidence="0.80",
            source=source,
            document=document,
            evidence_span=evidence,
        )
        event = models.Event.objects.create(
            actor_entity=duplicate,
            predicate="rebranded_as",
            object_entity=primary,
            confidence="0.80",
            source=source,
            document=document,
            evidence_span=evidence,
        )
        belief = models.Belief.objects.create(
            belief_type="identity",
            subject_entity=duplicate,
            predicate="same_as",
            object_entity=primary,
            truth_status=models.Belief.TruthStatus.TRUE_SUPPORTED,
            confidence="0.80",
            assumption_policy=policy,
        )

        result = merge_entities(primary, duplicate, reason="duplicate alias")
        claim.refresh_from_db()
        event.refresh_from_db()
        belief.refresh_from_db()
        duplicate.refresh_from_db()

        self.assertGreaterEqual(result.aliases_moved, 1)
        self.assertEqual(claim.subject_entity, primary)
        self.assertEqual(event.actor_entity, primary)
        self.assertEqual(belief.subject_entity, primary)
        self.assertEqual(duplicate.metadata_json["merged_into_entity_id"], primary.pk)
        self.assertTrue(models.EntityAlias.objects.filter(entity=primary, alias="FB").exists())
        if duplicate_mentions:
            duplicate_mentions[0].refresh_from_db()
            self.assertEqual(duplicate_mentions[0].entity, primary)

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

    def _document(self, text: str, source: models.Source | None = None) -> models.Document:
        active_source = source or self._source()
        result = persist_normalized_document(
            DocumentInput(
                source_id=active_source.pk,
                url=f"https://example.test/doc-{models.Document.objects.count()}",
                title="Entity test",
                raw_text=text,
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        )
        return result.document
