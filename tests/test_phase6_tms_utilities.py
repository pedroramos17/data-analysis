"""Phase 6 dependency-light truth maintenance status tests."""

from __future__ import annotations

import unittest
from decimal import Decimal

from sourceflow.tms.status import (
    JustificationInput,
    TmsError,
    resolve_truth_status,
)


class Phase6TruthStatusTests(unittest.TestCase):
    def test_full_support_resolves_true_supported(self) -> None:
        resolution = resolve_truth_status([JustificationInput("supports")])

        self.assertEqual(resolution.truth_status, "true_supported")
        self.assertEqual(resolution.confidence, Decimal("1"))
        self.assertFalse(resolution.is_disputed)

    def test_weak_support_resolves_partially_supported(self) -> None:
        resolution = resolve_truth_status(
            [JustificationInput("supports", weight=Decimal("0.4"))]
        )

        self.assertEqual(resolution.truth_status, "partially_supported")
        self.assertEqual(resolution.confidence, Decimal("0.40"))

    def test_contradiction_only_resolves_false_supported(self) -> None:
        resolution = resolve_truth_status([JustificationInput("contradicts")])

        self.assertEqual(resolution.truth_status, "false_supported")
        self.assertEqual(resolution.confidence, Decimal("1"))
        self.assertFalse(resolution.is_disputed)

    def test_mixed_evidence_marks_dispute_without_collapsing(self) -> None:
        resolution = resolve_truth_status(
            [
                JustificationInput("supports", weight=Decimal("3")),
                JustificationInput("contradicts", weight=Decimal("1")),
            ]
        )

        self.assertEqual(resolution.truth_status, "contradicted")
        self.assertTrue(resolution.is_disputed)
        self.assertEqual(resolution.confidence, Decimal("0.75"))
        self.assertEqual(resolution.supporting_weight, Decimal("3"))
        self.assertEqual(resolution.contradicting_weight, Decimal("1"))

    def test_rule_and_assumption_types_count_as_support(self) -> None:
        resolution = resolve_truth_status(
            [
                JustificationInput("derived_by_rule", weight=Decimal("0.6")),
                JustificationInput("assumption", weight=Decimal("0.4")),
            ]
        )

        self.assertEqual(resolution.truth_status, "true_supported")

    def test_inactive_justifications_are_ignored(self) -> None:
        resolution = resolve_truth_status(
            [
                JustificationInput("supports", is_active=False),
                JustificationInput("contradicts"),
            ]
        )

        self.assertEqual(resolution.truth_status, "false_supported")

    def test_no_active_evidence_follows_assumption_policy(self) -> None:
        owa = resolve_truth_status([], policy="OWA")
        cwa = resolve_truth_status([], policy="CWA")
        partial = resolve_truth_status(
            [JustificationInput("supports", is_active=False)], policy="PartialCWA"
        )

        self.assertEqual(owa.truth_status, "unknown")
        self.assertEqual(cwa.truth_status, "false_supported")
        self.assertEqual(partial.truth_status, "unknown")
        self.assertEqual(owa.confidence, Decimal("0"))

    def test_confidence_is_capped_at_one(self) -> None:
        resolution = resolve_truth_status(
            [JustificationInput("supports", weight=Decimal("5"))]
        )

        self.assertEqual(resolution.confidence, Decimal("1"))

    def test_invalid_inputs_raise(self) -> None:
        with self.assertRaises(TmsError):
            resolve_truth_status([JustificationInput("teleports")])
        with self.assertRaises(TmsError):
            resolve_truth_status([JustificationInput("supports", weight=Decimal("-1"))])
        with self.assertRaises(TmsError):
            resolve_truth_status([], full_support_weight=Decimal("0"))


if __name__ == "__main__":
    unittest.main()
