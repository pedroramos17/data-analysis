"""Phase 7 contradiction and diagnosis utility tests."""

from __future__ import annotations

import unittest
from decimal import Decimal

from sourceflow.reasoning.contradictions import (
    DISPUTE_STATUS,
    claim_key,
    claims_contradict,
    find_contradictory_claim_pairs,
    support_is_disputed,
)
from sourceflow.reasoning.diagnosis import AnomalyInput, diagnose_anomaly


class Phase7ContradictionDiagnosisUtilityTests(unittest.TestCase):
    def test_claim_key_and_contradiction_matching_are_dependency_light(self) -> None:
        positive = {
            "subject_id": "42",
            "predicate": "reports",
            "object_literal": "profit growth",
            "polarity": "positive",
        }
        negative = {
            "subject_id": "42",
            "predicate": "reports",
            "object_literal": "profit growth",
            "polarity": "negative",
        }

        self.assertEqual(claim_key(positive), claim_key(negative))
        self.assertTrue(claims_contradict(positive, negative))
        self.assertEqual(find_contradictory_claim_pairs([positive, negative]), [(positive, negative)])

    def test_support_is_disputed_checks_status_and_metadata(self) -> None:
        self.assertTrue(support_is_disputed({"status": "disputed"}))
        self.assertTrue(support_is_disputed({"metadata_json": {"dispute_status": DISPUTE_STATUS}}))

    def test_diagnosis_ranks_supported_hypotheses_and_lists_missing_evidence(self) -> None:
        hypotheses = diagnose_anomaly(
            AnomalyInput(
                anomaly_type="price_move",
                subject="PETR4",
                direction="down",
                magnitude=Decimal("0.05"),
                market_evidence={"volume_spike": "3x", "volatility_shock": "2x"},
            ),
            events=[
                {
                    "id": "event-1",
                    "event_type": "lawsuit",
                    "polarity": "negative",
                    "predicate": "faces",
                    "object_literal": "lawsuit",
                    "confidence": "0.8",
                }
            ],
            claims=[
                {
                    "id": "claim-1",
                    "polarity": "negative",
                    "predicate": "faces",
                    "object_literal": "lawsuit",
                    "status": "active",
                    "confidence": "0.8",
                }
            ],
            graph_edges=["event:1 -affects-> risk_factor:litigation_risk"],
        )

        self.assertGreaterEqual(hypotheses[0].confidence, hypotheses[1].confidence)
        self.assertIn("negative news pressure", hypotheses[0].hypothesis)
        self.assertTrue(hypotheses[0].supporting_evidence)
        self.assertEqual(hypotheses[0].graph_path, ("event:1 -affects-> risk_factor:litigation_risk",))
        self.assertTrue(all(hypothesis.missing_evidence is not None for hypothesis in hypotheses))


if __name__ == "__main__":
    unittest.main()
