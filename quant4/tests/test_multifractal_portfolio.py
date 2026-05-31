"""Quant4 multifractal Phase 10 portfolio tests."""

from __future__ import annotations

from django.test import SimpleTestCase


class Quant4MultifractalPortfolioTests(SimpleTestCase):
    """Portfolio optimizer should consume multifractal risk signals safely."""

    def test_weights_sum_to_budget(self) -> None:
        """Minimum-variance baseline returns a normalized allocation."""
        from quant4.services.multifractal.portfolio.multifractal_optimizer import (
            minimum_variance_weights,
        )

        weights = minimum_variance_weights(["AAA", "BBB"], [[0.04, 0.0], [0.0, 0.01]])

        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertGreater(weights["BBB"], weights["AAA"])

    def test_constraints_are_respected(self) -> None:
        """Max-weight constraints cap concentrated allocations."""
        from quant4.services.multifractal.portfolio.constraints import (
            MultifractalPortfolioConstraints,
        )
        from quant4.services.multifractal.portfolio.multifractal_optimizer import (
            optimize_multifractal_adjusted_portfolio,
        )

        result = optimize_multifractal_adjusted_portfolio(
            ["AAA", "BBB", "CCC"],
            [[0.01, 0.0, 0.0], [0.0, 0.04, 0.0], [0.0, 0.0, 0.05]],
            risk_features={},
            constraints=MultifractalPortfolioConstraints(max_weight=0.50),
        )

        self.assertLessEqual(max(result.weights.values()), 0.50)
        self.assertTrue(result.constraints_report["max_weight_ok"])

    def test_turbulent_assets_receive_lower_allocation(self) -> None:
        """Multifractal penalties reduce allocation to turbulent assets."""
        from quant4.services.multifractal.portfolio.multifractal_optimizer import (
            optimize_multifractal_adjusted_portfolio,
        )

        result = optimize_multifractal_adjusted_portfolio(
            ["CALM", "TURB"],
            [[0.02, 0.0], [0.0, 0.02]],
            risk_features={"TURB": {"delta_alpha": 1.0, "intermittency_proxy": 1.0}},
            regime_labels={"TURB": "turbulent_multifractal_regime"},
        )

        self.assertLess(result.weights["TURB"], result.weights["CALM"])
        self.assertFalse(result.to_json_dict()["claims_factor_validity"])

    def test_network_cluster_penalty_reduces_crowding(self) -> None:
        """Network-aware allocation reports cluster concentration."""
        from quant4.services.multifractal.portfolio.multifractal_optimizer import (
            optimize_multifractal_adjusted_portfolio,
        )

        result = optimize_multifractal_adjusted_portfolio(
            ["AAA", "BBB", "CCC"],
            [[0.02, 0.0, 0.0], [0.0, 0.02, 0.0], [0.0, 0.0, 0.02]],
            risk_features={},
            graph_clusters={"AAA": "cluster_1", "BBB": "cluster_1"},
        )

        self.assertIn("cluster_exposure", result.constraints_report)
