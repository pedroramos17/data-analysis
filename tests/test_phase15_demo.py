"""Phase 15 end-to-end demo tests.

Asserts the demo produces all ten required outputs and satisfies the
Definition-of-Done invariants, and that it runs from a single management command.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from sourceflow import models
from sourceflow.orchestration import run_end_to_end_demo


class Phase15DemoTests(TestCase):
    def test_demo_produces_all_ten_steps(self) -> None:
        report = run_end_to_end_demo()
        steps = report["steps"]

        # 1-4: ingest, link, claims, event
        self.assertEqual(len(steps["1_documents_ingested"]), 4)
        self.assertGreaterEqual(steps["2_entities_linked"]["mentions_linked"], 1)
        self.assertGreaterEqual(len(steps["3_claims_extracted"]), 3)
        self.assertEqual(steps["4_event_created"]["event_type"], "regulatory_action")

        # 5: source comparison reports omission under PartialCWA
        comparison = steps["5_source_comparison"]
        self.assertEqual(comparison["assumption_policy"], "PartialCWA")
        self.assertTrue(comparison["omissions"])
        self.assertFalse(comparison["omissions"][0]["inferred_false"])

        # 6 + 7: risk belief with supporting AND contradicting evidence
        belief = steps["6_risk_belief"]
        self.assertEqual(belief["belief_type"], "risk")
        self.assertGreaterEqual(belief["justification_count"], 2)
        self.assertTrue(steps["7_supporting_and_contradicting_evidence"]["supporting"])
        self.assertTrue(steps["7_supporting_and_contradicting_evidence"]["contradicting"])

        # 8: risk propagated to supplier and aggregated to the portfolio
        propagation = steps["8_risk_propagated"]
        self.assertTrue(propagation["direct_signals"])
        self.assertTrue(propagation["propagated_to_suppliers"])
        self.assertTrue(propagation["portfolio_aggregates"])

        # 9: proof-carrying GraphRAG answer
        answer = steps["9_graphrag_answer"]
        self.assertIn("answer", answer)
        self.assertTrue(answer["supporting_claims"])
        self.assertIn("what_would_change_this", answer)
        self.assertIn("confidence_breakdown", answer)

        # 10: portfolio exposure explanation
        explanation = steps["10_portfolio_explanation"]
        self.assertEqual(explanation["portfolio_id"], "demo-book")
        self.assertTrue(explanation["top_risk_contributors"])

    def test_definition_of_done_invariants_hold(self) -> None:
        invariants = run_end_to_end_demo()["invariants"]
        self.assertTrue(invariants["every_belief_has_justification"])
        self.assertTrue(invariants["every_conclusion_has_evidence"])
        self.assertTrue(invariants["graphrag_answer_carries_evidence"])
        self.assertTrue(invariants["contradiction_preserved_not_collapsed"])
        self.assertTrue(invariants["every_risk_path_auditable"])

    def test_runs_from_one_command(self) -> None:
        out = StringIO()
        call_command("demo_e2e", "--summary", stdout=out)
        output = out.getvalue()
        self.assertIn("DEFINITION OF DONE MET", output)
        self.assertIn("every_risk_path_auditable", output)
        # --keep would persist; default rolls back so the command stays repeatable.
        self.assertEqual(models.PipelineJob.objects.count(), 0)
        self.assertEqual(models.Belief.objects.count(), 0)
