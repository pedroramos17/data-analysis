"""Phase 6 truth maintenance persistence tests."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from sourceflow import models
from sourceflow.claims import extract_and_persist_document_claims
from sourceflow.entities import create_or_update_entity
from sourceflow.events import extract_and_persist_document_events
from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
from sourceflow.tms import (
    JustificationSpec,
    TmsError,
    create_belief,
    dependent_beliefs,
    recompute_belief,
    recompute_stale_beliefs,
    retract_belief,
    retract_claim,
    retract_event,
)

PROVENANCE = {"created_by": "sourceflow.tests.test_phase6_tms"}


class Phase6TruthMaintenanceTests(TestCase):
    def setUp(self) -> None:
        create_or_update_entity(canonical_name="Petrobras", entity_type="Company")

    def test_create_belief_persists_policy_justifications_and_truth_status(self) -> None:
        claim = self._claim("Petrobras faces a regulatory investigation.")

        belief = create_belief(
            belief_type="risk_exposure",
            predicate="under_regulatory_investigation",
            subject_entity=claim.subject_entity,
            justifications=[JustificationSpec("supports", claim=claim)],
            provenance=PROVENANCE,
        )

        self.assertEqual(belief.assumption_policy.code, "OWA")
        self.assertEqual(belief.truth_status, models.Belief.TruthStatus.TRUE_SUPPORTED)
        self.assertEqual(belief.confidence, Decimal("1"))
        self.assertEqual(belief.status, models.Belief.Status.ACTIVE)
        self.assertEqual(belief.provenance_json, PROVENANCE)
        justifications = list(belief.justifications.all())
        self.assertEqual(len(justifications), 1)
        self.assertEqual(justifications[0].supporting_claim, claim)
        self.assertEqual(justifications[0].provenance_json, PROVENANCE)

    def test_create_belief_requires_provenance_and_justifications(self) -> None:
        claim = self._claim("Petrobras faces a regulatory investigation.")

        with self.assertRaises(TmsError):
            create_belief(
                belief_type="risk_exposure",
                predicate="under_regulatory_investigation",
                justifications=[JustificationSpec("supports", claim=claim)],
                provenance={},
            )
        with self.assertRaises(TmsError):
            create_belief(
                belief_type="risk_exposure",
                predicate="under_regulatory_investigation",
                justifications=[],
                provenance=PROVENANCE,
            )
        with self.assertRaises(TmsError):
            create_belief(
                belief_type="risk_exposure",
                predicate="under_regulatory_investigation",
                justifications=[JustificationSpec("supports")],
                provenance=PROVENANCE,
            )
        self.assertEqual(models.Belief.objects.count(), 0)

    def test_contradictory_evidence_marks_dispute_without_collapsing(self) -> None:
        supporting = self._claim("Petrobras faces a regulatory investigation.")
        contradicting = self._claim("Petrobras denies a regulatory investigation.")

        belief = create_belief(
            belief_type="risk_exposure",
            predicate="under_regulatory_investigation",
            justifications=[
                JustificationSpec("supports", claim=supporting),
                JustificationSpec("contradicts", claim=contradicting),
            ],
            provenance=PROVENANCE,
        )

        self.assertEqual(belief.truth_status, models.Belief.TruthStatus.CONTRADICTED)
        self.assertEqual(belief.status, models.Belief.Status.ACTIVE)
        self.assertEqual(belief.justifications.count(), 2)

    def test_retract_claim_logs_audit_rows_and_marks_dependents_stale(self) -> None:
        claim = self._claim("Petrobras faces a regulatory investigation.")
        belief = create_belief(
            belief_type="risk_exposure",
            predicate="under_regulatory_investigation",
            justifications=[JustificationSpec("supports", claim=claim)],
            provenance=PROVENANCE,
        )

        result = retract_claim(claim, reason="source correction", provenance=PROVENANCE)

        claim.refresh_from_db()
        belief.refresh_from_db()
        self.assertEqual(claim.status, models.Claim.Status.RETRACTED)
        self.assertEqual(belief.status, models.Belief.Status.STALE)
        self.assertEqual([stale.pk for stale in result.stale_beliefs], [belief.pk])
        claim_log = models.RetractionLog.objects.get(target_type="claim")
        self.assertEqual(claim_log.affected_claim, claim)
        self.assertEqual(claim_log.previous_status, models.Claim.Status.ACTIVE)
        self.assertEqual(claim_log.new_status, "retracted")
        belief_log = models.RetractionLog.objects.get(target_type="belief")
        self.assertEqual(belief_log.affected_belief, belief)
        self.assertIn("source correction", belief_log.reason)

    def test_retraction_propagates_through_belief_chains(self) -> None:
        claim = self._claim("Petrobras faces a regulatory investigation.")
        base_belief = create_belief(
            belief_type="risk_exposure",
            predicate="under_regulatory_investigation",
            justifications=[JustificationSpec("supports", claim=claim)],
            provenance=PROVENANCE,
        )
        derived_belief = create_belief(
            belief_type="risk_exposure",
            predicate="elevated_compliance_risk",
            justifications=[JustificationSpec("supports", belief=base_belief)],
            provenance=PROVENANCE,
        )

        result = retract_claim(claim, reason="source correction", provenance=PROVENANCE)

        base_belief.refresh_from_db()
        derived_belief.refresh_from_db()
        self.assertEqual(base_belief.status, models.Belief.Status.STALE)
        self.assertEqual(derived_belief.status, models.Belief.Status.STALE)
        self.assertEqual(len(result.stale_beliefs), 2)

    def test_recompute_stale_beliefs_reactivates_with_fresh_truth_status(self) -> None:
        supporting = self._claim("Petrobras faces a regulatory investigation.")
        contradicting = self._claim("Petrobras denies a regulatory investigation.")
        belief = create_belief(
            belief_type="risk_exposure",
            predicate="under_regulatory_investigation",
            justifications=[
                JustificationSpec("supports", claim=supporting),
                JustificationSpec("contradicts", claim=contradicting),
            ],
            provenance=PROVENANCE,
        )
        self.assertEqual(belief.truth_status, models.Belief.TruthStatus.CONTRADICTED)

        retract_claim(contradicting, reason="publisher withdrew denial", provenance=PROVENANCE)
        recomputed = recompute_stale_beliefs()

        belief.refresh_from_db()
        self.assertEqual([entry[0].pk for entry in recomputed], [belief.pk])
        self.assertEqual(belief.status, models.Belief.Status.ACTIVE)
        self.assertEqual(belief.truth_status, models.Belief.TruthStatus.TRUE_SUPPORTED)

    def test_retract_event_logs_audit_row_and_inactivates_justifications(self) -> None:
        document = self._document("Petrobras faces a regulatory investigation.")
        event = extract_and_persist_document_events(document)[0].event
        belief = create_belief(
            belief_type="event_impact",
            predicate="regulatory_pressure",
            justifications=[JustificationSpec("supports", event=event)],
            provenance=PROVENANCE,
        )

        retract_event(event, reason="event misclassified", provenance=PROVENANCE)
        resolution = recompute_belief(belief)

        self.assertTrue(
            models.RetractionLog.objects.filter(target_type="event", affected_event=event).exists()
        )
        self.assertEqual(resolution.truth_status, models.Belief.TruthStatus.UNKNOWN)
        belief.refresh_from_db()
        self.assertEqual(belief.status, models.Belief.Status.STALE)
        self.assertEqual(belief.truth_status, models.Belief.TruthStatus.UNKNOWN)

    def test_retract_belief_marks_belief_retracted_and_dependents_stale(self) -> None:
        claim = self._claim("Petrobras faces a regulatory investigation.")
        base_belief = create_belief(
            belief_type="risk_exposure",
            predicate="under_regulatory_investigation",
            justifications=[JustificationSpec("supports", claim=claim)],
            provenance=PROVENANCE,
        )
        derived_belief = create_belief(
            belief_type="risk_exposure",
            predicate="elevated_compliance_risk",
            justifications=[JustificationSpec("supports", belief=base_belief)],
            provenance=PROVENANCE,
        )

        retract_belief(base_belief, reason="analyst withdrew inference", provenance=PROVENANCE)
        recompute_stale_beliefs()

        base_belief.refresh_from_db()
        derived_belief.refresh_from_db()
        self.assertEqual(base_belief.status, models.Belief.Status.RETRACTED)
        self.assertEqual(derived_belief.status, models.Belief.Status.ACTIVE)
        self.assertEqual(derived_belief.truth_status, models.Belief.TruthStatus.UNKNOWN)

    def test_dependent_beliefs_requires_exactly_one_referent(self) -> None:
        claim = self._claim("Petrobras faces a regulatory investigation.")

        with self.assertRaises(TmsError):
            dependent_beliefs()
        with self.assertRaises(TmsError):
            dependent_beliefs(claim=claim, event=claim)

    def test_retraction_requires_reason_and_provenance(self) -> None:
        claim = self._claim("Petrobras faces a regulatory investigation.")

        with self.assertRaises(TmsError):
            retract_claim(claim, reason=" ", provenance=PROVENANCE)
        with self.assertRaises(TmsError):
            retract_claim(claim, reason="source correction", provenance={})
        self.assertEqual(models.RetractionLog.objects.count(), 0)

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
                url=f"https://example.test/phase6-{models.Document.objects.count()}",
                title="Phase 6 truth maintenance",
                raw_text=text,
                published_at=timezone.now(),
            ),
            max_chunk_chars=120,
            chunk_overlap=0,
        )
        return result.document

    def _claim(self, text: str) -> models.Claim:
        document = self._document(text)
        return extract_and_persist_document_claims(document)[0].claim
