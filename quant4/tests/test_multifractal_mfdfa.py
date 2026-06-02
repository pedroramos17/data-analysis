"""Quant4 multifractal Phase 3 MF-DFA tests."""

from __future__ import annotations

import math
import random

from django.test import SimpleTestCase


class Quant4MFDFAAlgorithmTests(SimpleTestCase):
    """Research-grade MF-DFA should expose diagnostics and stable spectra."""

    def test_monofractal_gaussian_series_has_narrow_spectrum(self) -> None:
        """Gaussian returns produce finite H(2) and a conservative spectrum width."""
        from quant4.services.multifractal.core.mfdfa import run_mfdfa

        config = _test_config()
        result = run_mfdfa(_seeded_gaussian_returns(512, 17), config)

        self.assertGreater(result.spectrum.hurst_h2, 0.2)
        self.assertLess(result.spectrum.hurst_h2, 1.0)
        self.assertLess(result.spectrum.spectrum_width, 0.9)
        self.assertEqual(result.valid_scale_count, 4)

    def test_multiplicative_cascade_has_wider_spectrum(self) -> None:
        """A binomial cascade has wider alpha support than Gaussian returns."""
        from quant4.services.multifractal.core.mfdfa import run_mfdfa

        config = _test_config()
        gaussian = run_mfdfa(_seeded_gaussian_returns(512, 23), config)
        cascade = run_mfdfa(_multiplicative_cascade(9, 0.72), config)

        self.assertGreater(
            cascade.spectrum.spectrum_width,
            gaussian.spectrum.spectrum_width,
        )
        self.assertGreater(cascade.spectrum.tau_nonlinearity, 0.0)

    def test_shuffled_clustered_series_reduces_multifractal_width(self) -> None:
        """Shuffling preserves values while weakening correlation-driven width."""
        from quant4.services.multifractal.core.mfdfa import run_mfdfa
        from quant4.services.multifractal.preprocessing.surrogates import (
            shuffled_returns,
        )

        config = _test_config()
        original = _clustered_gaussian_returns(512, 31)
        shuffled = shuffled_returns(original, seed=31)

        original_result = run_mfdfa(original, config)
        shuffled_result = run_mfdfa(shuffled, config)

        self.assertLessEqual(
            shuffled_result.spectrum.spectrum_width,
            original_result.spectrum.spectrum_width,
        )

    def test_q_zero_branch_is_numerically_stable(self) -> None:
        """The q=0 logarithmic averaging branch returns finite diagnostics."""
        from quant4.services.multifractal.core.mfdfa import run_mfdfa
        from quant4.services.multifractal.core.types import MFDFAConfig

        result = run_mfdfa(
            _seeded_gaussian_returns(256, 7),
            MFDFAConfig(q_grid=(-2.0, 0.0, 2.0), scales=(8, 16, 32)),
        )

        self.assertIn("0", result.spectrum.hq)
        self.assertTrue(math.isfinite(result.spectrum.hq["0"]))
        self.assertGreater(result.diagnostics_by_q["0"].r_squared, 0.0)

    def test_invalid_inputs_raise_useful_errors(self) -> None:
        """Short, non-finite, and invalid detrending requests fail clearly."""
        from quant4.services.multifractal.core.mfdfa import run_mfdfa
        from quant4.services.multifractal.core.types import MFDFAConfig

        with self.assertRaisesRegex(ValueError, "expected at least"):
            run_mfdfa([1.0, 2.0, 3.0])

        with self.assertRaisesRegex(ValueError, "finite numeric series"):
            run_mfdfa([1.0, float("nan"), 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])

        with self.assertRaisesRegex(ValueError, "detrending_order"):
            run_mfdfa(
                [float(index) for index in range(64)],
                MFDFAConfig(detrending_order=-1),
            )

        with self.assertRaisesRegex(ValueError, "segments"):
            run_mfdfa(
                [float(index) for index in range(64)],
                MFDFAConfig(scales=(8, 16, 40), min_segments_per_scale=4),
            )


def _test_config() -> object:
    from quant4.services.multifractal.core.types import MFDFAConfig

    return MFDFAConfig(q_grid=(-4.0, -2.0, 0.0, 2.0, 4.0), scales=(8, 16, 32, 64))


def _seeded_gaussian_returns(length: int, seed: int) -> list[float]:
    chooser = random.Random(seed)
    return [chooser.gauss(0.0, 1.0) for _index in range(length)]


def _clustered_gaussian_returns(length: int, seed: int) -> list[float]:
    chooser = random.Random(seed)
    return [
        chooser.gauss(0.0, 0.3 + 1.2 * (math.sin(index / 19.0) ** 2))
        for index in range(length)
    ]


def _multiplicative_cascade(levels: int, probability: float) -> list[float]:
    values = [1.0]
    for _level in range(levels):
        values = _cascade_step(values, probability)
    center = sum(values) / len(values)
    return [value - center for value in values]


def _cascade_step(values: list[float], probability: float) -> list[float]:
    expanded: list[float] = []
    for value in values:
        expanded.extend([value * probability, value * (1.0 - probability)])
    return expanded
