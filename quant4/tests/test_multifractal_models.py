"""Quant4 multifractal Phase 6 model tests."""

from __future__ import annotations

from django.test import SimpleTestCase


class Quant4MultifractalResearchModelTests(SimpleTestCase):
    """MSM, MMAR, and MRW models should be seeded research simulators."""

    def test_msm_simulation_is_seeded_and_shapes_are_stable(self) -> None:
        """MSM simulation returns returns, volatility, and latent state paths."""
        from quant4.services.multifractal.models.msm import (
            MSMParameters,
            simulate_msm_returns,
        )

        params = MSMParameters(component_count=3, base_volatility=0.02)
        left = simulate_msm_returns(params, steps=12, seed=17)
        right = simulate_msm_returns(params, steps=12, seed=17)

        self.assertEqual(left.returns, right.returns)
        self.assertEqual(len(left.returns), 12)
        self.assertEqual(len(left.volatility_path), 12)
        self.assertEqual(len(left.latent_states), 12)

    def test_msm_forecast_volatility_distribution_is_ordered(self) -> None:
        """MSM volatility forecast reports ordered deterministic quantiles."""
        from quant4.services.multifractal.models.msm import (
            MSMParameters,
            forecast_msm_volatility_distribution,
        )

        forecast = forecast_msm_volatility_distribution(
            MSMParameters(component_count=2, base_volatility=0.015),
            horizon=8,
            path_count=20,
            seed=21,
        )

        self.assertLessEqual(forecast.quantiles["p05"], forecast.quantiles["p50"])
        self.assertLessEqual(forecast.quantiles["p50"], forecast.quantiles["p95"])
        self.assertEqual(forecast.horizon, 8)

    def test_msm_parameters_validate_inputs(self) -> None:
        """Invalid MSM parameters fail with the offending field."""
        from quant4.services.multifractal.models.msm import MSMParameters

        with self.assertRaisesRegex(ValueError, "component_count"):
            MSMParameters(component_count=0)

        with self.assertRaisesRegex(ValueError, "base_volatility"):
            MSMParameters(base_volatility=0.0)

    def test_mmar_simulation_and_calibration_placeholder_are_explicit(self) -> None:
        """MMAR exposes simulation and a non-overclaiming calibration placeholder."""
        from quant4.services.multifractal.models.mmar import (
            MMARParameters,
            calibrate_mmar_placeholder,
            simulate_mmar_returns,
        )

        result = simulate_mmar_returns(MMARParameters(), steps=10, seed=19)
        calibration = calibrate_mmar_placeholder([0.01, -0.02, 0.03])

        self.assertEqual(len(result.returns), 10)
        self.assertEqual(len(result.time_deformation), 10)
        self.assertEqual(calibration.status, "CALIBRATION_PLACEHOLDER")
        self.assertIn("not full MMAR calibration", calibration.message)

    def test_mrw_simulation_and_intermittency_estimate_are_seeded(self) -> None:
        """MRW simulation is reproducible and estimates non-negative intermittency."""
        from quant4.services.multifractal.models.mrw import (
            MRWParameters,
            estimate_mrw_intermittency,
            simulate_mrw_returns,
        )

        params = MRWParameters(intermittency=0.12, base_volatility=0.02)
        left = simulate_mrw_returns(params, steps=16, seed=23)
        right = simulate_mrw_returns(params, steps=16, seed=23)
        estimate = estimate_mrw_intermittency(left.returns)

        self.assertEqual(left.returns, right.returns)
        self.assertEqual(len(left.volatility_path), 16)
        self.assertGreaterEqual(estimate.intermittency, 0.0)
        self.assertIn("scaling", estimate.method)
