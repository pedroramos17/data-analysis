"""Phase 10 dependency-light quant reasoning tests."""

from __future__ import annotations

import unittest
from decimal import Decimal

from sourceflow.quant import (
    RISK_TYPES,
    RiskGraph,
    RiskSignal,
    RuleBasedRegimeDetector,
    build_feature_matrix,
    explain_portfolio_risk,
    generate_event_alpha_candidates,
    load_risk_rules,
)
from sourceflow.quant.risk_graph import PortfolioRiskAggregate


class Phase10QuantUtilityTests(unittest.TestCase):
    def test_risk_rules_include_required_risk_types(self) -> None:
        rules = load_risk_rules()

        self.assertIn("legal_risk", RISK_TYPES)
        self.assertTrue(any(rule.risk_type == "legal_risk" for rule in rules))

    def test_negative_company_event_increases_direct_risk(self) -> None:
        signals = RiskGraph().propagate_event_risk(
            {
                "pk": "event-1",
                "event_type": "lawsuit",
                "polarity": "negative",
                "confidence": "0.80",
                "actor_entity_id": "entity-1",
            }
        )

        risk_types = {signal.risk_type for signal in signals}
        self.assertIn("legal_risk", risk_types)
        legal = next(signal for signal in signals if signal.risk_type == "legal_risk")
        self.assertEqual(legal.subject_id, "entity-1")
        self.assertGreater(legal.score, Decimal("0"))
        self.assertTrue(legal.graph_path)

    def test_event_alpha_candidates_include_backtest_spec_and_reasoning(self) -> None:
        candidates = generate_event_alpha_candidates(
            [
                {
                    "pk": "event-1",
                    "event_type": "regulatory_action",
                    "polarity": "negative",
                    "confidence": "0.75",
                    "actor_entity_id": "entity-1",
                    "actor_entity": {"sector": "energy"},
                    "source": {"reliability_score": "0.90"},
                }
            ],
            sector_reactions={"energy": Decimal("-0.02")},
        )

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.direction, "short")
        self.assertEqual(candidate.entry_horizon, "next_open_to_1d")
        self.assertIn("holding_period_days", candidate.to_backtest_spec())
        self.assertTrue(candidate.reasoning_trail)

    def test_regime_detector_accepts_feature_matrix_and_triggers_recompute(self) -> None:
        matrix = build_feature_matrix(
            [
                {"volatility": "0.2", "liquidity": "0.8", "return": "0.01", "kg_risk": "0.1"},
                {"volatility": "0.8", "liquidity": "0.2", "return": "-0.04", "kg_risk": "0.6"},
            ]
        )

        result = RuleBasedRegimeDetector().detect(matrix, linked_beliefs=("belief-1",))

        self.assertIn(result.dominant_regime, result.regime_probabilities)
        self.assertEqual(result.linked_belief_ids, ("belief-1",))
        self.assertTrue(result.trigger_risk_recompute)

    def test_portfolio_explanation_lists_risk_contributors_and_hedges(self) -> None:
        signal = RiskSignal(
            risk_type="legal_risk",
            subject_type="portfolio",
            subject_id="book-1",
            score=Decimal("0.40"),
            explanation="portfolio exposure aggregates legal risk",
            graph_path=("event:1 -has_actor-> entity:10", "portfolio:book-1 -holds-> exposed_entity:10"),
            source_evidence=({"event_id": 1, "evidence_text": "lawsuit"},),
            rule_id="portfolio_exposure_aggregation",
        )
        aggregate = PortfolioRiskAggregate("book-1", "legal_risk", Decimal("0.40"), (signal,), "aggregate legal risk")

        explanation = explain_portfolio_risk("book-1", aggregates=[aggregate], positions=[])

        self.assertEqual(explanation.portfolio_id, "book-1")
        self.assertEqual(explanation.top_risk_contributors[0].risk_factors, ("legal_risk",))
        self.assertIn("reduce_single_name_exposure", explanation.top_risk_contributors[0].suggested_hedge_candidates)
        self.assertTrue(explanation.top_risk_contributors[0].source_evidence)


if __name__ == "__main__":
    unittest.main()
