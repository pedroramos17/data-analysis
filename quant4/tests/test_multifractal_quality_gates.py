"""Quant4 multifractal Phase 15 quality-gate tests."""

from __future__ import annotations

from django.test import SimpleTestCase


class Quant4MultifractalQualityGateTests(SimpleTestCase):
    """Synthetic generators and quality gates should be deterministic."""

    def test_synthetic_generators_are_seed_reproducible(self) -> None:
        """Seeded synthetic series produce repeatable outputs."""
        from quant4.services.multifractal.synthetic import (
            gaussian_random_walk,
            heavy_tailed_returns,
            multiplicative_cascade,
        )

        self.assertEqual(
            gaussian_random_walk(8, seed=1),
            gaussian_random_walk(8, seed=1),
        )
        self.assertEqual(
            heavy_tailed_returns(8, seed=2),
            heavy_tailed_returns(8, seed=2),
        )
        self.assertEqual(
            multiplicative_cascade(3, seed=3),
            multiplicative_cascade(3, seed=3),
        )

    def test_synthetic_generators_have_expected_shapes(self) -> None:
        """Synthetic generators return shapes needed by downstream modules."""
        from quant4.services.multifractal.synthetic import (
            price_volume_pair,
            regime_switching_volatility,
            synthetic_lob_snapshots,
        )

        prices, volumes = price_volume_pair(16, seed=4)
        regimes = regime_switching_volatility(16, seed=5)
        snapshots = synthetic_lob_snapshots(16, seed=6)

        self.assertEqual(len(prices), 16)
        self.assertEqual(len(volumes), 16)
        self.assertEqual(len(regimes), 16)
        self.assertEqual(len(snapshots), 16)

    def test_quality_gate_matrix_has_required_commands(self) -> None:
        """Quality gates document the local validation command matrix."""
        from quant4.services.multifractal.quality_gates import quality_gate_matrix

        gates = quality_gate_matrix()
        commands = [gate.command for gate in gates]

        self.assertIn(".\\.venv-win\\Scripts\\python.exe manage.py check", commands)
        self.assertTrue(any("manage.py test quant4" in command for command in commands))
        self.assertFalse(any("live" in command.lower() for command in commands))

    def test_integration_smoke_runs_across_modules(self) -> None:
        """Synthetic data feeds core, risk, regime, portfolio, and LOB modules."""
        from quant4.services.multifractal.quality_gates import run_integration_smoke

        result = run_integration_smoke(seed=11)

        self.assertTrue(result["mfdfa_ok"])
        self.assertTrue(result["risk_ok"])
        self.assertTrue(result["regime_ok"])
        self.assertTrue(result["portfolio_ok"])
        self.assertTrue(result["lob_ok"])
        self.assertFalse(result["claims_predictive_performance"])

    def test_shared_defaults_and_regime_helper_are_used_by_modules(self) -> None:
        """Reports and quality gates expose the shared defaults/helper boundary."""
        import quant4.services.multifractal.quality_gates as quality_gates
        import quant4.services.multifractal.reports.multifractal_report as reports
        from quant4.services.multifractal.defaults import DEFAULT_DIAGNOSTIC_SEED
        from quant4.services.multifractal.regime.features import (
            build_regime_feature_rows,
        )

        self.assertEqual(DEFAULT_DIAGNOSTIC_SEED, 17)
        self.assertIs(reports.build_regime_feature_rows, build_regime_feature_rows)
        self.assertIs(
            quality_gates.build_regime_feature_rows,
            build_regime_feature_rows,
        )
