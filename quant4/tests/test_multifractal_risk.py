"""Quant4 multifractal Phase 8 risk tests."""

from __future__ import annotations

import random

from django.test import SimpleTestCase


class Quant4MultifractalRiskTests(SimpleTestCase):
    """Risk services should separate traditional and multifractal components."""

    def test_var_output_is_monotonic_with_confidence_level(self) -> None:
        """Higher confidence produces larger historical loss VaR."""
        from quant4.services.multifractal.risk.var import historical_var

        returns = [-0.01, -0.02, -0.03, 0.01, 0.02, -0.08, 0.03]

        self.assertGreater(
            historical_var(returns, 0.95),
            historical_var(returns, 0.80),
        )

    def test_var_and_expected_shortfall_are_zero_without_losses(self) -> None:
        """All-positive samples have zero historical loss VaR and ES."""
        from quant4.services.multifractal.risk.var import (
            expected_shortfall,
            historical_var,
        )

        returns = [0.01, 0.02, 0.03, 0.04]

        self.assertEqual(historical_var(returns, 0.95), 0.0)
        self.assertEqual(expected_shortfall(returns, 0.95), 0.0)

    def test_expected_shortfall_averages_losses_beyond_var(self) -> None:
        """Expected shortfall averages the historical tail losses."""
        from quant4.services.multifractal.risk.var import expected_shortfall

        returns = [-0.01, -0.02, -0.10, 0.03]

        self.assertGreaterEqual(expected_shortfall(returns, 0.80), 0.10)

    def test_risk_score_increases_with_volatility_and_intermittency(self) -> None:
        """Multifractal risk score responds to volatility and intermittency."""
        from quant4.services.multifractal.risk.multifractal_risk import (
            compute_asset_multifractal_risk,
        )

        calm = compute_asset_multifractal_risk(
            [0.001, -0.001, 0.002, -0.001],
            {"delta_alpha": 0.1, "intermittency_proxy": 0.1},
        )
        turbulent = compute_asset_multifractal_risk(
            [0.03, -0.05, 0.04, -0.06],
            {"delta_alpha": 0.8, "intermittency_proxy": 0.7},
        )

        self.assertGreater(turbulent.risk_score, calm.risk_score)
        self.assertIn("forecast_risk", turbulent.to_json_dict())
        self.assertIn("multifractal_risk", turbulent.to_json_dict())

    def test_rolling_risk_features_do_not_look_ahead(self) -> None:
        """Rolling risk rows are bounded by their historical window end."""
        from quant4.services.multifractal.risk.multifractal_risk import (
            compute_rolling_multifractal_risk,
        )

        rows = compute_rolling_multifractal_risk(
            "SPY",
            _seeded_returns(80, 11),
            {"delta_alpha": 0.2, "intermittency_proxy": 0.3},
            window_size=32,
            step=16,
        )

        self.assertEqual(rows[0]["window_start"], 0)
        self.assertEqual(rows[0]["window_end"], 31)
        self.assertTrue(all(row["window_start"] <= row["window_end"] for row in rows))

    def test_risk_report_has_separate_sections_and_caution(self) -> None:
        """Risk reports separate risk classes and avoid prediction claims."""
        from quant4.services.multifractal.risk.multifractal_risk import (
            compute_asset_multifractal_risk,
        )
        from quant4.services.multifractal.risk.reports import build_risk_report

        assessment = compute_asset_multifractal_risk(
            _seeded_returns(64, 5),
            {"delta_alpha": 0.3, "intermittency_proxy": 0.4},
        )
        report = build_risk_report("SPY", assessment)
        payload = report.to_json_dict()

        self.assertIn("forecast_risk", payload["sections"])
        self.assertIn("portfolio_risk", payload["sections"])
        self.assertIn("liquidity_risk", payload["sections"])
        self.assertIn("model_risk", payload["sections"])
        self.assertIn("regime_risk", payload["sections"])
        self.assertIn("not a prediction", report.to_markdown())


def _seeded_returns(length: int, seed: int) -> list[float]:
    chooser = random.Random(seed)
    return [chooser.gauss(0.0, 0.02) for _index in range(length)]
