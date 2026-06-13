"""Quant multifractal Phase 10 portfolio tests."""

from __future__ import annotations

from django.test import SimpleTestCase


class QuantMultifractalPortfolioTests(SimpleTestCase):
    """Portfolio optimizer should consume multifractal risk signals safely."""

    def test_weights_sum_to_budget(self) -> None:
        """Minimum-variance baseline returns a normalized allocation."""
        from quant.services.multifractal.portfolio.multifractal_optimizer import (
            minimum_variance_weights,
        )

        weights = minimum_variance_weights(["AAA", "BBB"], [[0.04, 0.0], [0.0, 0.01]])

        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertGreater(weights["BBB"], weights["AAA"])

    def test_constraints_are_respected(self) -> None:
        """Max-weight constraints cap concentrated allocations."""
        from quant.services.multifractal.portfolio.constraints import (
            MultifractalPortfolioConstraints,
        )
        from quant.services.multifractal.portfolio.multifractal_optimizer import (
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
        from quant.services.multifractal.portfolio.multifractal_optimizer import (
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
        from quant.services.multifractal.portfolio.multifractal_optimizer import (
            optimize_multifractal_adjusted_portfolio,
        )

        result = optimize_multifractal_adjusted_portfolio(
            ["AAA", "BBB", "CCC"],
            [[0.02, 0.0, 0.0], [0.0, 0.02, 0.0], [0.0, 0.0, 0.02]],
            risk_features={},
            graph_clusters={"AAA": "cluster_1", "BBB": "cluster_1"},
        )

        self.assertIn("cluster_exposure", result.constraints_report)

    def test_infeasible_cluster_limit_fails_clearly(self) -> None:
        """Cluster limits are never bypassed by optimizer fallback."""
        from quant.services.multifractal.portfolio.constraints import (
            MultifractalPortfolioConstraints,
        )
        from quant.services.multifractal.portfolio.multifractal_optimizer import (
            optimize_multifractal_adjusted_portfolio,
        )

        with self.assertRaisesRegex(ValueError, "Invalid cluster exposure"):
            optimize_multifractal_adjusted_portfolio(
                ["AAA", "BBB"],
                [[0.02, 0.0], [0.0, 0.02]],
                risk_features={},
                constraints=MultifractalPortfolioConstraints(cluster_limit=0.80),
                graph_clusters={"AAA": "cluster_1", "BBB": "cluster_1"},
            )

    def test_constraints_report_uses_caller_constraints(self) -> None:
        """Constraint reports include the actual constraint envelope used."""
        from quant.services.multifractal.portfolio.constraints import (
            MultifractalPortfolioConstraints,
        )
        from quant.services.multifractal.portfolio.multifractal_optimizer import (
            optimize_multifractal_adjusted_portfolio,
        )

        result = optimize_multifractal_adjusted_portfolio(
            ["AAA", "BBB"],
            [[0.02, 0.0], [0.0, 0.03]],
            risk_features={},
            constraints=MultifractalPortfolioConstraints(
                max_weight=0.70,
                cluster_limit=0.90,
            ),
            graph_clusters={"AAA": "cluster_1", "BBB": "cluster_2"},
        )

        self.assertTrue(result.constraints_report["cluster_limit_ok"])
        self.assertTrue(result.constraints_report["asset_class_limit_ok"])
        self.assertEqual(result.constraints_report["constraints"]["max_weight"], 0.70)
        self.assertEqual(
            result.constraints_report["constraints"]["cluster_limit"],
            0.90,
        )

    def test_infeasible_asset_class_limit_fails_clearly(self) -> None:
        """Asset-class limits are enforced when metadata is provided."""
        from quant.services.multifractal.portfolio.constraints import (
            MultifractalPortfolioConstraints,
        )
        from quant.services.multifractal.portfolio.multifractal_optimizer import (
            optimize_multifractal_adjusted_portfolio,
        )

        with self.assertRaisesRegex(ValueError, "Invalid asset_class exposure"):
            optimize_multifractal_adjusted_portfolio(
                ["AAA", "BBB"],
                [[0.02, 0.0], [0.0, 0.02]],
                risk_features={},
                constraints=MultifractalPortfolioConstraints(
                    asset_class_limits={"stock": 0.80}
                ),
                asset_metadata={
                    "AAA": {"asset_class": "stock"},
                    "BBB": {"asset_class": "stock"},
                },
            )
