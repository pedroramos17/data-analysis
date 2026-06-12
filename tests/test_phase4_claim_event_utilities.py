"""Phase 4 dependency-light claim and event utility tests."""

from __future__ import annotations

import unittest
from decimal import Decimal

from sourceflow.claims import ClaimCandidate, extract_claims, validate_claim_candidate
from sourceflow.events import classify_event_type, default_event_impact, extract_events


class Phase4ClaimEventUtilityTests(unittest.TestCase):
    def test_heuristic_claim_extractor_extracts_structured_claims(self) -> None:
        text = (
            "Petrobras faces a regulatory investigation. "
            "Vale reports lower iron ore output. "
            "Fed signals rate cut delay."
        )

        claims = extract_claims(text)

        self.assertEqual(len(claims), 3)
        self.assertEqual(claims[0].subject_text, "Petrobras")
        self.assertEqual(claims[0].predicate, "faces")
        self.assertEqual(claims[0].object_literal, "a regulatory investigation")
        self.assertEqual(claims[0].polarity, "negative")
        self.assertEqual(claims[2].modality, "forecasted")
        self.assertTrue(claims[0].evidence_text.startswith("Petrobras faces"))

    def test_claim_validator_rejects_missing_required_fields(self) -> None:
        result = validate_claim_candidate(
            ClaimCandidate(
                subject_text="",
                predicate="faces",
                object_literal="regulatory investigation",
                evidence_text="",
            )
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.status, "incomplete")
        self.assertIn("missing_subject", result.errors)
        self.assertIn("missing_evidence", result.errors)

    def test_event_classifier_maps_financial_event_types(self) -> None:
        self.assertEqual(
            classify_event_type("faces", "regulatory investigation"),
            "regulatory_action",
        )
        self.assertEqual(classify_event_type("reports", "lower iron ore output"), "earnings")
        self.assertEqual(classify_event_type("signals", "rate cut delay"), "guidance")

    def test_heuristic_event_extractor_adds_impact_metadata(self) -> None:
        events = extract_events("Petrobras faces a regulatory investigation.")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actor_text, "Petrobras")
        self.assertEqual(events[0].event_type, "regulatory_action")
        self.assertEqual(events[0].polarity, "negative")
        self.assertIn("regulatory_risk", events[0].metadata_json["risk_channels"])

    def test_default_event_impact_is_auditable(self) -> None:
        impact = default_event_impact("regulatory_action", "negative")

        self.assertEqual(impact.magnitude, Decimal("-0.30"))
        self.assertIn("regulatory_risk", impact.risk_channels)


if __name__ == "__main__":
    unittest.main()
