"""Phase 7 inference engine persistence tests."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from sourceflow import models
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.reasoning import InferenceEngine, RuleDefinition


class Phase7InferenceEngineTests(TestCase):
    def setUp(self) -> None:
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")

    def test_rule_engine_creates_belief_with_rule_and_source_support(self) -> None:
        event = self._event("Petrobras faces a lawsuit.")
        engine = InferenceEngine.from_default_rules()

        results = engine.infer_from_event(event)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "created")
        belief = results[0].belief
        rule = models.InferenceRule.objects.get(rule_id="legal_event_increases_risk")
        self.assertEqual(belief.created_by_rule, rule)
        self.assertEqual(belief.belief_type, "risk")
        self.assertEqual(belief.predicate, "increases")
        self.assertEqual(belief.object_literal, "litigation_risk")
        self.assertEqual(belief.subject_entity, event.actor_entity)
        self.assertEqual(belief.provenance_json["rule_id"], "legal_event_increases_risk")
        self.assertEqual(belief.provenance_json["support_type"], "Event")
        self.assertEqual(belief.provenance_json["support_id"], str(event.pk))
        self.assertEqual(belief.provenance_json["source_id"], event.source_id)
        self.assertEqual(belief.provenance_json["evidence_span_id"], event.evidence_span_id)
        justification = belief.justifications.get()
        self.assertEqual(justification.support_type, models.Justification.SupportType.DERIVED_BY_RULE)
        self.assertEqual(justification.supporting_event, event)
        self.assertEqual(justification.rule, rule)
        self.assertEqual(justification.weight, Decimal("0.980"))

    def test_default_rule_exception_blocks_conclusion(self) -> None:
        event = self._event("Petrobras faces an immaterial amount.")
        event.event_type = models.Event.EventType.LAWSUIT
        event.polarity = models.Claim.Polarity.NEGATIVE
        event.object_literal = "immaterial amount"
        event.save(update_fields=["event_type", "polarity", "object_literal", "updated_at"])
        engine = InferenceEngine.from_default_rules()

        results = engine.infer_from_event(event)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "blocked_by_exception")
        self.assertEqual(models.Belief.objects.count(), 0)
        self.assertTrue(models.InferenceRule.objects.filter(rule_id="legal_event_increases_risk").exists())

    def test_deductive_rule_uses_full_support_weight(self) -> None:
        event = self._event("Petrobras faces a regulatory investigation.")
        definition = RuleDefinition.from_mapping(
            {
                "id": "regulatory_action_implies_compliance_risk",
                "type": "deductive",
                "when": [{"event_type": "regulatory_action"}, {"polarity": "negative"}],
                "then": [
                    {
                        "belief_type": "risk",
                        "predicate": "increases",
                        "object": "compliance_risk",
                    }
                ],
                "confidence_delta": -0.8,
            }
        )

        result = InferenceEngine([definition]).infer_from_event(event)[0]

        self.assertEqual(result.belief.truth_status, models.Belief.TruthStatus.TRUE_SUPPORTED)
        self.assertEqual(result.belief.justifications.get().weight, Decimal("1.000"))

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
                url=f"https://example.test/phase7-{models.Document.objects.count()}",
                title="Phase 7 inference",
                raw_text=text,
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        )
        return result.document

    def _event(self, text: str) -> models.Event:
        return extract_and_persist_document_events(self._document(text))[0].event
