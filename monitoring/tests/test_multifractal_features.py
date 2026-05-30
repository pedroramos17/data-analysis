"""Tests for finance multifractal feature functions."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings


class MultifractalFeatureTests(SimpleTestCase):
    """Pure-numpy multifractal helpers are deterministic and guarded."""

    def test_returns_and_roughness_features(self) -> None:
        """Log returns, volatility, and path roughness handle basic prices."""
        from sourceflow.finance_features.multifractal.returns import (
            log_return,
            realized_volatility,
        )
        from sourceflow.finance_features.multifractal.roughness import path_roughness

        prices = [100.0, 102.0, 101.0, 105.0]

        self.assertAlmostEqual(log_return(100.0, 102.0), 0.019802, places=5)
        self.assertGreater(realized_volatility(prices), 0.0)
        self.assertGreater(path_roughness(prices), 1.0)

    def test_mfdfa_and_wavelet_energy_baselines(self) -> None:
        """MF-DFA and Haar wavelet features return finite core metrics."""
        from sourceflow.finance_features.multifractal.feature_builder import (
            build_multifractal_feature_set,
        )

        features = build_multifractal_feature_set([100, 101, 103, 102, 105, 107])

        self.assertEqual(features["method"], "mfdfa_wavelet")
        self.assertIn("2", features["hurst_json"])
        self.assertGreaterEqual(features["spectrum_width"], 0.0)
        self.assertIn("haar_level_1", features["wavelet_energy_json"])

    @override_settings(SOURCEFLOW_FEATURE_FLAGS={"FIN_MULTIFRACTAL_EMD": False})
    def test_emd_feature_is_disabled_without_flag(self) -> None:
        """EMD/IMF extraction cannot run accidentally when disabled."""
        from sourceflow.config.feature_flags import FeatureDisabledError
        from sourceflow.finance_features.multifractal.emd import imf_energy_features

        with self.assertRaisesRegex(FeatureDisabledError, "FIN_MULTIFRACTAL_EMD"):
            imf_energy_features([1, 2, 3, 4])
