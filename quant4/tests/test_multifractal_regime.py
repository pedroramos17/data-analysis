"""Quant4 multifractal Phase 9 regime tests."""

from __future__ import annotations

import random

from django.test import SimpleTestCase


class Quant4MultifractalRegimeTests(SimpleTestCase):
    """Regime services should detect shifts without future leakage."""

    def test_synthetic_regime_shift_is_detected(self) -> None:
        """A low-to-high multifractal shift receives turbulent labels."""
        from quant4.services.multifractal.regime.multifractal_regime import (
            detect_multifractal_regimes,
        )

        rows = _feature_rows([0.10] * 30 + [0.90] * 30)

        report = detect_multifractal_regimes(rows, window_size=16)

        self.assertEqual(
            report.labels[-1].label,
            "turbulent_multifractal_regime",
        )
        self.assertTrue(report.change_points)

    def test_labels_are_stable_under_small_noise(self) -> None:
        """Small feature perturbations should not rewrite calm labels."""
        from quant4.services.multifractal.regime.multifractal_regime import (
            detect_multifractal_regimes,
        )

        base = detect_multifractal_regimes(_feature_rows([0.12] * 40))
        noisy = detect_multifractal_regimes(_feature_rows(_noisy_levels(40)))

        self.assertEqual(base.labels[-1].label, noisy.labels[-1].label)

    def test_regime_labels_do_not_look_ahead(self) -> None:
        """Each label records the latest training index it was allowed to use."""
        from quant4.services.multifractal.regime.multifractal_regime import (
            detect_multifractal_regimes,
        )

        report = detect_multifractal_regimes(_feature_rows([0.15] * 24 + [0.7]))

        self.assertTrue(
            all(label.training_end_index <= label.index for label in report.labels)
        )

    def test_transition_table_and_markdown_are_serializable(self) -> None:
        """Reports expose JSON and human-readable regime diagnostics."""
        from quant4.services.multifractal.regime.multifractal_regime import (
            detect_multifractal_regimes,
        )

        report = detect_multifractal_regimes(_feature_rows([0.08] * 12 + [0.75] * 12))
        payload = report.to_json_dict()

        self.assertIn("transition_table", payload)
        self.assertIn("not a trading signal", report.to_markdown())


def _feature_rows(levels: list[float]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for _index, level in enumerate(levels):
        rows.append(
            {
                "hurst_h2": 0.5 + level * 0.1,
                "delta_alpha": level,
                "spectrum_asymmetry": level * 0.2,
                "tau_nonlinearity": level,
                "realized_volatility": level * 0.04,
                "drawdown": -level * 0.05,
            }
        )
    return rows


def _noisy_levels(length: int) -> list[float]:
    chooser = random.Random(19)
    return [0.12 + chooser.uniform(-0.01, 0.01) for _index in range(length)]
