"""Quant portfolio optimization MVP tests."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase


class QuantPortfolioOptimizerTests(TestCase):
    """Portfolio optimizers should be local-first and constraint-aware."""

    def test_weights_sum_to_expected_budget(self) -> None:
        """Equal-weight and covariance-backed optimizers respect budget."""
        from quant.services.portfolio.optimizers import (
            EqualWeightOptimizer,
            MinimumVarianceOptimizer,
        )
        from quant.services.risk.covariance import covariance_shrinkage

        equal = EqualWeightOptimizer().optimize(["AAA", "BBB", "CCC"])
        covariance = covariance_shrinkage([[0.01, -0.02], [0.03, 0.01]])
        minimum_variance = MinimumVarianceOptimizer().optimize(
            ["AAA", "BBB"],
            covariance,
        )

        self.assertAlmostEqual(sum(equal.weights.values()), 1.0)
        self.assertAlmostEqual(sum(minimum_variance.weights.values()), 1.0)

    def test_constraints_are_respected(self) -> None:
        """Max Sharpe prototype caps concentrated weights by constraints."""
        from quant.services.portfolio.constraints import PortfolioConstraints
        from quant.services.portfolio.optimizers import MaxSharpePrototypeOptimizer

        constraints = PortfolioConstraints(max_weight=0.6)
        result = MaxSharpePrototypeOptimizer().optimize(
            symbols=["AAA", "BBB"],
            expected_returns={"AAA": 0.20, "BBB": 0.01},
            covariance=[[0.01, 0.0], [0.0, 0.04]],
            constraints=constraints,
        )

        self.assertLessEqual(result.weights["AAA"], 0.6)
        self.assertAlmostEqual(sum(result.weights.values()), 1.0)

    def test_liquidity_constraint_can_reject_infeasible_portfolio(self) -> None:
        """Liquidity limits reject overweight target allocations."""
        from quant.services.portfolio.constraints import (
            PortfolioConstraints,
            validate_portfolio_constraints,
        )

        constraints = PortfolioConstraints(liquidity_limits={"AAA": 0.10})

        with self.assertRaisesRegex(ValueError, "AAA"):
            validate_portfolio_constraints({"AAA": 0.20, "BBB": 0.80}, constraints)

    def test_transaction_cost_drag_is_calculated(self) -> None:
        """Transaction cost drag uses turnover and portfolio value."""
        from quant.services.portfolio.transaction_costs import (
            TransactionCostModel,
            calculate_transaction_cost_drag,
        )

        drag = calculate_transaction_cost_drag(
            current_weights={"AAA": 0.5, "BBB": 0.5},
            target_weights={"AAA": 0.6, "BBB": 0.4},
            portfolio_value=1000.0,
            model=TransactionCostModel(bps_per_turnover=10.0),
        )

        self.assertAlmostEqual(drag["turnover"], 0.2)
        self.assertAlmostEqual(drag["estimated_cost"], 0.2)


class QuantPortfolioPersistenceTests(TestCase):
    """Portfolio runs should persist reusable research artifacts."""

    def test_portfolio_run_stores_paths_metrics_and_risk_report(self) -> None:
        """The portfolio command writes weights/trades and run metadata."""
        from quant.models import PortfolioRun

        with TemporaryDirectory() as output_dir:
            call_command(
                "quant_optimize_portfolio",
                "--name",
                "portfolio-smoke",
                "--symbols",
                "AAA,BBB",
                "--optimizer",
                "equal_weight",
                "--current-weights-json",
                json.dumps({"AAA": 0.4, "BBB": 0.6}),
                "--output-dir",
                output_dir,
                "--data-start",
                "2024-01-01",
                "--data-end",
                "2024-01-31",
                "--split-start",
                "2024-01-31",
                "--split-end",
                "2024-01-31",
                stdout=StringIO(),
            )
            run = PortfolioRun.objects.get(name="portfolio-smoke")
            weights_payload = json.loads(Path(run.weights_path).read_text())

        self.assertTrue(run.trades_path.endswith("trades.json"))
        self.assertAlmostEqual(sum(weights_payload["weights"].values()), 1.0)
        self.assertIn("turnover", run.metrics_json)
        self.assertEqual(run.risk_report_json["claim_scope"], "portfolio_research")


class QuantPortfolioOptionalBackendTests(TestCase):
    """Optional portfolio backends should fail clearly when unavailable."""

    def test_optional_portfolio_backends_fail_clearly(self) -> None:
        """CVXPY, Riskfolio, and PyPortfolioOpt wrappers identify dependencies."""
        from quant.services.portfolio.cvxpy_backend import CVaROptimizer
        from quant.services.portfolio.pyportfolioopt_backend import (
            PyPortfolioOptOptimizer,
        )
        from quant.services.portfolio.riskfolio_backend import RiskfolioOptimizer
        from quant.services.registry import OptionalDependencyMissingError

        with self.assertRaisesRegex(OptionalDependencyMissingError, "cvxpy"):
            CVaROptimizer(required_module="missing_quant_cvxpy").optimize()
        with self.assertRaisesRegex(OptionalDependencyMissingError, "riskfolio"):
            RiskfolioOptimizer(required_module="missing_quant_riskfolio").optimize()
        with self.assertRaisesRegex(OptionalDependencyMissingError, "pyportfolioopt"):
            PyPortfolioOptOptimizer(
                required_module="missing_quant_pyportfolioopt"
            ).optimize()
