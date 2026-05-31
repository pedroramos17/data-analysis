"""Quant4 multifractal Phase 5 method tests."""

from __future__ import annotations

import math
import random

from django.test import SimpleTestCase


class Quant4AdditionalMultifractalMethodTests(SimpleTestCase):
    """Additional multifractal methods should share core result conventions."""

    def test_mfdma_modes_return_common_summary_interface(self) -> None:
        """MF-DMA supports backward, centered, and forward moving averages."""
        from quant4.services.multifractal.core.mfdma import run_mfdma

        for mode in ("backward", "centered", "forward"):
            result = run_mfdma(_seeded_returns(192, 7), _test_config(), mode)

            self.assertEqual(result.method, "mfdma")
            self.assertEqual(result.metadata["moving_average_mode"], mode)
            self.assertIn("delta_alpha", result.summary)
            self.assertIn("2", result.spectrum.hq)
            self.assertEqual(result.valid_scale_count, 3)

    def test_mfdma_invalid_mode_fails_clearly(self) -> None:
        """Unsupported MF-DMA moving-average modes are rejected."""
        from quant4.services.multifractal.core.mfdma import run_mfdma

        with self.assertRaisesRegex(ValueError, "moving_average_mode"):
            run_mfdma(_seeded_returns(128, 8), _test_config(), "diagonal")

    def test_mfdcca_outputs_joint_metrics_without_future_windows(self) -> None:
        """MF-DCCA returns q-cross fluctuations and explicit segment bounds."""
        from quant4.services.multifractal.core.mfdcca import run_mfdcca

        left, right = _correlated_pair(192)
        result = run_mfdcca(left, right, _test_config())

        self.assertEqual(result.method, "mfdcca")
        self.assertIn("2", result.q_cross_fluctuations)
        self.assertIn("joint_hurst_h2", result.joint_metrics)
        self.assertGreater(result.joint_metrics["cross_correlation_mean"], 0.0)
        for scale, bounds in result.segment_bounds_by_scale.items():
            scale_value = int(scale)
            self.assertTrue(all(end < len(left) for _start, end in bounds))
            self.assertTrue(
                all(end - start + 1 == scale_value for start, end in bounds)
            )

    def test_partition_function_requires_positive_measure(self) -> None:
        """Partition-function baseline accepts positive measures and rejects others."""
        from quant4.services.multifractal.core.partition import run_partition_function

        measure = [abs(value) + 0.01 for value in _seeded_returns(192, 9)]
        result = run_partition_function(measure, _test_config())

        self.assertEqual(result.method, "partition_function")
        self.assertTrue(result.metadata["positive_measure"])
        self.assertGreaterEqual(result.spectrum.spectrum_width, 0.0)

        with self.assertRaisesRegex(ValueError, "positive measure"):
            run_partition_function([1.0, 0.0, 2.0, 3.0], _test_config())

    def test_wavelet_diagnostics_use_optional_backend_or_local_fallback(self) -> None:
        """Wavelet diagnostics return energies without requiring PyWavelets."""
        from quant4.services.multifractal.core.wavelet import run_wavelet_diagnostics

        result = run_wavelet_diagnostics(_sine_returns(96), scales=(2, 4, 8))

        self.assertIn(result.method, {"pywavelets_cwt", "ricker_fallback"})
        self.assertEqual(set(result.energy_by_scale), {"2", "4", "8"})
        self.assertIn(result.dominant_scale, (2, 4, 8))
        self.assertIn("not_wavelet_leader_spectrum", result.limitations)


def _test_config() -> object:
    from quant4.services.multifractal.core.types import MFDFAConfig

    return MFDFAConfig(q_grid=(-2.0, 0.0, 2.0), scales=(8, 16, 32))


def _seeded_returns(length: int, seed: int) -> list[float]:
    chooser = random.Random(seed)
    return [chooser.gauss(0.0, 1.0) for _index in range(length)]


def _correlated_pair(length: int) -> tuple[list[float], list[float]]:
    left = _seeded_returns(length, 11)
    chooser = random.Random(12)
    right = [0.7 * value + 0.3 * chooser.gauss(0.0, 1.0) for value in left]
    return left, right


def _sine_returns(length: int) -> list[float]:
    return [
        math.sin(index / 5.0) + 0.1 * math.sin(index / 2.0)
        for index in range(length)
    ]
