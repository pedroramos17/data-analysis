"""Quant4 MVP2 risk and regime tests."""

from __future__ import annotations

from datetime import date

from django.test import TestCase


class Quant4RegimeCoreTests(TestCase):
    """Regime detectors must be leakage-safe and local-first."""

    def test_regime_labels_use_only_past_training_data(self) -> None:
        """A late volatility shock does not relabel earlier observations."""
        from quant4.services.regimes.detectors import rolling_volatility_regime

        labels = rolling_volatility_regime(
            [0.01, 0.01, 0.01, 0.01, 0.01, 0.50],
            window=3,
            high_threshold=0.10,
        )

        self.assertEqual([label.label for label in labels[:5]], ["calm"] * 5)
        self.assertEqual(labels[-1].label, "volatile")
        self.assertEqual(labels[-1].training_end_index, 5)

    def test_optional_ruptures_detector_fails_clearly(self) -> None:
        """Missing optional rupture dependency identifies the detector."""
        from quant4.services.regimes.optional import detect_ruptures_regime
        from quant4.services.registry import OptionalDependencyMissingError

        with self.assertRaisesRegex(OptionalDependencyMissingError, "ruptures"):
            detect_ruptures_regime([0.01, 0.02, -0.03])


class Quant4RiskCoreTests(TestCase):
    """Risk services should persist separated research sections."""

    def test_risk_run_stores_metrics_json(self) -> None:
        """Risk analysis persists forecast, portfolio, liquidity, model, regime."""
        from quant4.models import RiskRun
        from quant4.services.risk.reports import run_risk_analysis

        run = run_risk_analysis(
            name="risk-smoke",
            returns=[0.01, -0.02, 0.015, -0.03],
            prices=[100.0, 98.0, 99.0, 96.0],
            volumes=[1000.0, 1100.0, 900.0, 950.0],
            data_range=(date(2024, 1, 1), date(2024, 1, 4)),
            split_range=(date(2024, 1, 3), date(2024, 1, 4)),
            random_seed=11,
        )

        stored = RiskRun.objects.get(pk=run.pk)
        self.assertEqual(stored.random_seed, 11)
        self.assertEqual(stored.data_start, date(2024, 1, 1))
        self.assertEqual(stored.split_end, date(2024, 1, 4))
        self.assertEqual(stored.feature_schema_json["returns"], "past_sequence_float")
        self.assertIn("forecast_risk", stored.metrics_json)
        self.assertIn("portfolio_risk", stored.metrics_json)
        self.assertIn("liquidity_risk", stored.metrics_json)
        self.assertIn("model_risk", stored.metrics_json)
        self.assertIn("regime_risk", stored.metrics_json)

    def test_stress_report_stores_scenario_outputs(self) -> None:
        """Stress reports store named scenario output sections."""
        from quant4.models import ExplainabilityReport
        from quant4.services.risk.stress_testing import build_stress_report

        report = build_stress_report(
            name="stress-smoke",
            returns=[0.01, -0.02, 0.015, -0.03],
            scenarios=["2008", "COVID"],
            data_range=(date(2024, 1, 1), date(2024, 1, 4)),
            split_range=(date(2024, 1, 3), date(2024, 1, 4)),
        )

        stored = ExplainabilityReport.objects.get(pk=report.pk)
        self.assertEqual(stored.data_end, date(2024, 1, 4))
        self.assertEqual(
            stored.feature_schema_json["scenarios"],
            "named_research_scenarios",
        )
        self.assertIn("2008", stored.report_json["scenarios"])
        self.assertIn("COVID", stored.report_json["scenarios"])
        self.assertEqual(stored.report_json["claim_scope"], "research_risk_only")

    def test_liquidity_risk_works_without_lob_data_using_fallback(self) -> None:
        """No LOB rows still yields Amihud-style liquidity metadata."""
        from quant4.services.risk.liquidity_risk import estimate_liquidity_risk

        metrics = estimate_liquidity_risk(
            returns=[0.01, -0.02, 0.015],
            volumes=[1000.0, 1200.0, 800.0],
        )

        self.assertEqual(metrics["method"], "amihud_fallback")
        self.assertFalse(metrics["bid_ask_spread_available"])
        self.assertGreaterEqual(metrics["amihud_illiquidity"], 0)

    def test_model_risk_fields_exist_but_do_not_overclaim_causality(self) -> None:
        """Model-risk metadata is explicit and rejects causality claims."""
        from quant4.services.risk.risk_attribution import build_model_risk_fields

        fields = build_model_risk_fields("pca_risk")

        self.assertFalse(fields["causality_claim"])
        self.assertIn("limitations", fields)
        self.assertNotIn("causal discovery", str(fields).lower())
