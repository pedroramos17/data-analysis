"""Phase 1 canonical schema and assumption policy tests."""

from __future__ import annotations

from django.contrib import admin
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.reasoning import assumptions


CANONICAL_MODELS = (
    models.ProviderOwner,
    models.Source,
    models.Document,
    models.DocumentChunk,
    models.Entity,
    models.EntityAlias,
    models.EntityMention,
    models.Claim,
    models.Event,
    models.EvidenceSpan,
    models.KnowledgeEdge,
    models.AssumptionPolicy,
    models.Belief,
    models.Justification,
    models.InferenceRule,
    models.RetractionLog,
    models.RetrievalTrace,
    models.RiskFactor,
    models.Asset,
    models.Instrument,
    models.PortfolioPosition,
)


class CanonicalSchemaCrudTests(TestCase):
    """Canonical Phase 1 models should support CRUD and provenance."""

    def test_every_model_has_timestamps_and_provenance(self) -> None:
        for model in CANONICAL_MODELS:
            with self.subTest(model=model.__name__):
                fields = {field.name for field in model._meta.fields}

                self.assertTrue(
                    {"created_at", "updated_at", "metadata_json", "provenance_json"}.issubset(fields)
                )

    def test_canonical_models_create_read_update(self) -> None:
        records = self._create_canonical_records()

        for record in records:
            model = type(record)
            with self.subTest(model=model.__name__):
                fetched = model.objects.get(pk=record.pk)
                fetched.metadata_json = {"updated": model.__name__}
                fetched.save(update_fields=["metadata_json"])
                fetched.refresh_from_db()

                self.assertEqual(fetched.metadata_json["updated"], model.__name__)

    def test_extracted_facts_link_to_source_document_and_evidence(self) -> None:
        records = self._create_canonical_records()
        claim = self._by_model(records, models.Claim)
        event = self._by_model(records, models.Event)
        belief = self._by_model(records, models.Belief)

        self.assertIsNotNone(claim.source_id)
        self.assertIsNotNone(claim.document_id)
        self.assertIsNotNone(claim.evidence_span_id)
        self.assertIsNotNone(event.source_id)
        self.assertIsNotNone(event.document_id)
        self.assertIsNotNone(event.evidence_span_id)
        self.assertTrue(
            belief.justifications.filter(supporting_claim=claim, supporting_event=event).exists()
        )

    def test_canonical_models_are_registered_in_admin(self) -> None:
        for model in CANONICAL_MODELS:
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)

    def _create_canonical_records(self) -> list[models.TimestampedProvenanceModel]:
        owner = models.ProviderOwner.objects.create(
            name="Example Owner",
            canonical_name="example owner",
            provenance_json={"test": "phase1"},
        )
        source = models.Source.objects.create(
            name="Example News",
            url="https://example.test/feed.xml",
            provider_owner=owner,
            source_type=models.Source.SourceType.RSS,
            country="BR",
            language="en",
            reliability_score="0.80",
            bias_tags=["business"],
            provenance_json={"test": "phase1"},
        )
        document = models.Document.objects.create(
            source=source,
            url="https://example.test/petrobras-investigation",
            title="Petrobras faces regulatory investigation",
            published_at=timezone.now(),
            raw_text="Petrobras faces a regulatory investigation.",
            clean_text="Petrobras faces a regulatory investigation.",
            content_hash="doc-hash",
            language="en",
            provenance_json={"test": "phase1"},
        )
        chunk = models.DocumentChunk.objects.create(
            document=document,
            chunk_index=0,
            text=document.clean_text,
            char_start=0,
            char_end=len(document.clean_text),
            token_count=5,
            content_hash="chunk-hash",
            provenance_json={"test": "phase1"},
        )
        evidence = models.EvidenceSpan.objects.create(
            source=source,
            document=document,
            chunk=chunk,
            text="Petrobras faces a regulatory investigation",
            char_start=0,
            char_end=41,
            extractor_name="unit-test",
            extractor_version="1",
            confidence="0.95",
            provenance_json={"test": "phase1"},
        )
        entity = models.Entity.objects.create(
            canonical_name="Petrobras",
            entity_type="Company",
            external_ids_json={"ticker": "PETR4"},
            country="BR",
            sector="Energy",
            confidence="0.98",
            provenance_json={"test": "phase1"},
        )
        regulator = models.Entity.objects.create(
            canonical_name="Brazil regulator",
            entity_type="Regulator",
            country="BR",
            confidence="0.90",
            provenance_json={"test": "phase1"},
        )
        alias = models.EntityAlias.objects.create(
            entity=entity,
            alias="PETR4",
            alias_normalized="petr4",
            alias_type="ticker",
            namespace="B3",
            provenance_json={"test": "phase1"},
        )
        mention = models.EntityMention.objects.create(
            document=document,
            chunk=chunk,
            entity=entity,
            evidence_span=evidence,
            mention_text="Petrobras",
            entity_type="Company",
            char_start=0,
            char_end=9,
            confidence="0.98",
            extractor_name="unit-test",
            provenance_json={"test": "phase1"},
        )
        owa_policy = models.AssumptionPolicy.objects.create(
            code=models.AssumptionPolicy.PolicyCode.OWA,
            name="Open world",
            scope="news",
            is_default=True,
            provenance_json={"test": "phase1"},
        )
        cwa_policy = models.AssumptionPolicy.objects.create(
            code=models.AssumptionPolicy.PolicyCode.CWA,
            name="Closed world",
            scope="portfolio_position",
            provenance_json={"test": "phase1"},
        )
        rule = models.InferenceRule.objects.create(
            rule_id="legal_event_increases_risk",
            name="Legal event increases risk",
            rule_type=models.InferenceRule.RuleType.RISK_PROPAGATION,
            definition_json={"when": [{"event_type": "regulatory_action"}]},
            assumption_policy=owa_policy,
            confidence_delta="0.200",
            provenance_json={"test": "phase1"},
        )
        claim = models.Claim.objects.create(
            subject_entity=entity,
            predicate="faces",
            object_entity=regulator,
            object_literal="regulatory investigation",
            polarity=models.Claim.Polarity.NEGATIVE,
            modality=models.Claim.Modality.ASSERTED,
            tense="present",
            confidence="0.91",
            source=source,
            document=document,
            evidence_span=evidence,
            status=models.Claim.Status.ACTIVE,
            provenance_json={"test": "phase1"},
        )
        event = models.Event.objects.create(
            actor_entity=entity,
            predicate="faces",
            object_entity=regulator,
            object_literal="regulatory investigation",
            event_type=models.Event.EventType.REGULATORY_ACTION,
            event_time=timezone.now(),
            polarity=models.Claim.Polarity.NEGATIVE,
            magnitude="0.3000",
            confidence="0.89",
            source=source,
            document=document,
            evidence_span=evidence,
            provenance_json={"test": "phase1"},
        )
        edge = models.KnowledgeEdge.objects.create(
            edge_type="ASSERTS",
            source_node_type="Source",
            source_node_id=str(source.pk),
            target_node_type="Claim",
            target_node_id=str(claim.pk),
            confidence="0.91",
            source_document=document,
            evidence_span=evidence,
            provenance_json={"test": "phase1"},
        )
        belief = models.Belief.objects.create(
            belief_type="risk",
            subject_entity=entity,
            predicate="increases",
            object_literal="regulatory_risk",
            truth_status=models.Belief.TruthStatus.TRUE_SUPPORTED,
            confidence="0.80",
            assumption_policy=owa_policy,
            created_by_rule=rule,
            valid_from=timezone.now(),
            status=models.Belief.Status.ACTIVE,
            provenance_json={"test": "phase1"},
        )
        justification = models.Justification.objects.create(
            belief=belief,
            support_type=models.Justification.SupportType.SUPPORTS,
            supporting_claim=claim,
            supporting_event=event,
            rule=rule,
            weight="1.000",
            provenance_json={"test": "phase1"},
        )
        retraction = models.RetractionLog.objects.create(
            target_type="claim",
            target_id=str(claim.pk),
            reason="unit-test correction",
            previous_status=models.Claim.Status.ACTIVE,
            new_status=models.Claim.Status.RETRACTED,
            source=source,
            document=document,
            affected_claim=claim,
            affected_event=event,
            affected_belief=belief,
            provenance_json={"test": "phase1"},
        )
        trace = models.RetrievalTrace.objects.create(
            query="Why did Petrobras risk increase?",
            query_hash="query-hash",
            retriever_name="unit-test",
            retrieval_mode="hybrid",
            results_json=[{"claim_id": claim.pk}],
            citations_json=[{"evidence_span_id": evidence.pk}],
            assumptions_json=[owa_policy.code],
            retrieval_confidence="0.80",
            extraction_confidence="0.91",
            reasoning_confidence="0.75",
            provenance_json={"test": "phase1"},
        )
        risk_factor = models.RiskFactor.objects.create(
            name="regulatory_risk",
            risk_type="regulatory_risk",
            description="Regulatory exposure",
            confidence="0.90",
            provenance_json={"test": "phase1"},
        )
        asset = models.Asset.objects.create(
            symbol="PETR4",
            name="Petrobras PN",
            asset_type="equity",
            country="BR",
            sector="Energy",
            currency="BRL",
            external_ids_json={"ticker": "PETR4"},
            confidence="0.95",
            provenance_json={"test": "phase1"},
        )
        instrument = models.Instrument.objects.create(
            asset=asset,
            symbol="PETR4",
            instrument_type="equity",
            exchange="B3",
            currency="BRL",
            external_ids_json={"ticker": "PETR4"},
            provenance_json={"test": "phase1"},
        )
        position = models.PortfolioPosition.objects.create(
            portfolio_id="book-a",
            asset=asset,
            instrument=instrument,
            quantity="10.00000000",
            market_value="350.00000000",
            currency="BRL",
            assumption_policy=cwa_policy,
            provenance_json={"test": "phase1"},
        )
        return [
            owner,
            source,
            document,
            chunk,
            entity,
            alias,
            mention,
            claim,
            event,
            evidence,
            edge,
            owa_policy,
            belief,
            justification,
            rule,
            retraction,
            trace,
            risk_factor,
            asset,
            instrument,
            position,
        ]

    def _by_model(self, records: list[object], model: type[object]) -> object:
        for record in records:
            if isinstance(record, model):
                return record
        raise AssertionError(f"Missing record for {model.__name__}")


class AssumptionPolicyResolutionTests(SimpleTestCase):
    def test_news_defaults_to_open_world(self) -> None:
        self.assertEqual(
            assumptions.resolve_assumption_policy("news"),
            assumptions.AssumptionPolicyCode.OWA,
        )

        result = assumptions.evaluate_missing_fact(assumptions.AssumptionPolicyCode.OWA)

        self.assertEqual(result.truth_status, "unknown")
        self.assertFalse(result.can_infer_absence)

    def test_internal_tables_can_infer_absence_under_cwa(self) -> None:
        policy = assumptions.resolve_assumption_policy("portfolio_position")
        result = assumptions.evaluate_missing_fact(policy)

        self.assertEqual(policy, assumptions.AssumptionPolicyCode.CWA)
        self.assertEqual(result.truth_status, "false_supported")
        self.assertTrue(result.can_infer_absence)

    def test_source_coverage_uses_partial_cwa_without_global_falsehood(self) -> None:
        policy = assumptions.resolve_assumption_policy("source_coverage")
        result = assumptions.evaluate_missing_fact(policy)

        self.assertEqual(policy, assumptions.AssumptionPolicyCode.PARTIAL_CWA)
        self.assertEqual(result.truth_status, "unknown")
        self.assertFalse(result.can_infer_absence)
        self.assertIn("omission", result.explanation)

    def test_entity_identity_assumptions_are_contextual(self) -> None:
        self.assertEqual(
            assumptions.resolve_assumption_policy("entity", identifier_type="ticker"),
            assumptions.AssumptionPolicyCode.UNIQUE_NAME,
        )
        self.assertEqual(
            assumptions.resolve_assumption_policy("entity", ambiguous_name=True),
            assumptions.AssumptionPolicyCode.NO_UNIQUE_NAME,
        )
