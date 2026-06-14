"""Quant multifractal Phase 4 diagnostics tests."""

from __future__ import annotations

import json
import math
import random

from django.test import SimpleTestCase


class QuantMultifractalDiagnosticTests(SimpleTestCase):
    """MF-DFA diagnostics should be local, reproducible, and serializable."""

    def test_shuffled_test_reduces_correlation_driven_multifractality(self) -> None:
        """Shuffled comparison weakens clustered volatility multifractality."""
        from quant.services.multifractal.core.stat_tests import (
            run_shuffled_comparison,
        )

        report = run_shuffled_comparison(
            _clustered_gaussian_returns(256, 31),
            _test_config(),
            seed=31,
        )

        self.assertEqual(report.method, "shuffled")
        self.assertLessEqual(report.delta_metrics["delta_alpha"], 0.0)
        self.assertLessEqual(report.ratio_metrics["delta_alpha"], 1.0)

    def test_finite_size_report_warns_on_short_samples(self) -> None:
        """Short samples produce explicit finite-size diagnostics."""
        from quant.services.multifractal.core.stat_tests import run_finite_size_check

        report = run_finite_size_check(
            _seeded_gaussian_returns(80, 11),
            _short_config(),
            seed=19,
            simulation_count=3,
        )

        self.assertTrue(report.is_short_sample)
        self.assertIn("finite_size_warning", report.warnings)
        self.assertIn("synthetic_delta_alpha_mean", report.to_json_dict())

    def test_bootstrap_intervals_are_reproducible_with_seed(self) -> None:
        """Bootstrap confidence intervals are deterministic for the same seed."""
        from quant.services.multifractal.core.stat_tests import (
            bootstrap_confidence_intervals,
        )

        left = bootstrap_confidence_intervals(
            _seeded_gaussian_returns(160, 7),
            _test_config(),
            seed=41,
            bootstrap_count=6,
        )
        right = bootstrap_confidence_intervals(
            _seeded_gaussian_returns(160, 7),
            _test_config(),
            seed=41,
            bootstrap_count=6,
        )

        self.assertEqual(left.to_json_dict(), right.to_json_dict())
        self.assertIn("hurst_h2", left.intervals)
        self.assertIn("delta_alpha", left.intervals)

    def test_extreme_value_sensitivity_preserves_observation_count(self) -> None:
        """Extreme-value sensitivity caps values without silent row deletion."""
        from quant.services.multifractal.core.stat_tests import (
            run_extreme_value_sensitivity,
        )

        series = _seeded_gaussian_returns(160, 5)
        series[40] = 12.0
        report = run_extreme_value_sensitivity(series, _test_config())

        self.assertEqual(report.original_count, len(series))
        self.assertEqual(report.adjusted_count, len(series))
        self.assertGreaterEqual(report.sensitivity_score, 0.0)
        self.assertEqual(report.method, "winsorized")

    def test_diagnostics_report_is_json_serializable_and_markdown_ready(self) -> None:
        """Aggregate diagnostics return JSON and human-readable markdown."""
        from quant.services.multifractal.core.diagnostics import (
            run_multifractal_diagnostics,
        )

        report = run_multifractal_diagnostics(
            _clustered_gaussian_returns(160, 13),
            _test_config(),
            seed=23,
            bootstrap_count=4,
            finite_size_simulations=2,
        )

        payload = report.to_json_dict()
        markdown = report.to_markdown()

        self.assertIn(report.attribution, _allowed_attributions())
        self.assertIn("shuffled", payload["comparisons"])
        self.assertIn("# Multifractal Diagnostics", markdown)
        self.assertIsInstance(json.dumps(payload), str)


def _test_config() -> object:
    from quant.services.multifractal.core.types import MFDFAConfig

    return MFDFAConfig(q_grid=(-2.0, 0.0, 2.0), scales=(8, 16, 32))


def _short_config() -> object:
    from quant.services.multifractal.core.types import MFDFAConfig

    return MFDFAConfig(
        q_grid=(-2.0, 0.0, 2.0),
        scales=(8, 16),
        min_scale_count=2,
    )


def _seeded_gaussian_returns(length: int, seed: int) -> list[float]:
    chooser = random.Random(seed)
    return [chooser.gauss(0.0, 1.0) for _index in range(length)]


def _clustered_gaussian_returns(length: int, seed: int) -> list[float]:
    chooser = random.Random(seed)
    return [
        chooser.gauss(0.0, 0.2 + 1.4 * (math.sin(index / 13.0) ** 2))
        for index in range(length)
    ]


def _allowed_attributions() -> set[str]:
    return {
        "likely_correlation_driven",
        "likely_distribution_driven",
        "likely_finite_size_artifact",
        "likely_extreme_value_dominated",
        "robust_multifractal_evidence",
        "inconclusive",
    }
