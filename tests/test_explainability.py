"""Tests for Phase 14 explainability and alpha diagnostics."""

from __future__ import annotations

import unittest

from src.models.baselines import NaiveReturnBaseline
from src.models.base import ForecastPrediction
from src.models.explainability import (
    ALPHA_VALIDATION_FIELDS,
    SIGNAL_EXPLANATION_FIELDS,
    alpha_validation_metrics,
)
from src.models.inference.batch_predict import run_batch_prediction, signal_row


class ExplainabilityTests(unittest.TestCase):
    """Signals should carry lightweight non-black-box diagnostics."""

    def test_batch_prediction_adds_required_signal_explanation_fields(self) -> None:
        dataset = [
            {
                "asset_id": 1,
                "symbol": "SPY",
                "ts": "2024-01-01",
                "close": 100.0,
                "volume": 1000.0,
                "log_return": 0.01,
                "volatility_regime": "low_vol",
                "realized_volatility_20": 0.2,
            },
            {
                "asset_id": 1,
                "symbol": "SPY",
                "ts": "2024-01-02",
                "close": 101.0,
                "volume": 1100.0,
                "log_return": 0.02,
                "volatility_regime": "low_vol",
                "realized_volatility_20": 0.18,
            },
        ]
        model = NaiveReturnBaseline().fit(dataset, {})

        result = run_batch_prediction(
            model,
            [dataset[-1]],
            "1d",
            feature_set_version="phase14_v1",
        )
        explanation = result.predictions[0].explanation_json
        persisted = signal_row(result.predictions[0])["explanation_json"]

        for field in SIGNAL_EXPLANATION_FIELDS:
            self.assertIn(field, explanation)
            self.assertIn(field, persisted)
        self.assertEqual(explanation["feature_set_version"], "phase14_v1")
        self.assertEqual(explanation["model_name"], "naive_return_baseline")
        self.assertTrue(explanation["top_features"])
        self.assertEqual(explanation["regime_context"]["volatility_regime"], "low_vol")
        self.assertIn("realized_volatility_20", explanation["risk_context"])

    def test_alpha_validation_metrics_cover_acceptance_contract(self) -> None:
        rows = [
            {"symbol": "SPY", "log_return": 0.01, "regime": "risk_on"},
            {"symbol": "QQQ", "log_return": -0.02, "regime": "risk_off"},
            {"symbol": "SPY", "log_return": 0.03, "regime": "risk_on"},
            {"symbol": "QQQ", "log_return": -0.01, "regime": "risk_off"},
        ]
        predictions = [
            ForecastPrediction("SPY", "2024-01-02", "1d", 0.02, 0.02),
            ForecastPrediction("QQQ", "2024-01-02", "1d", -0.01, -0.01),
        ]

        metrics = alpha_validation_metrics(rows, predictions, existing_signals=[0.1, -0.1])

        for field in ALPHA_VALIDATION_FIELDS:
            self.assertIn(field, metrics)
        self.assertGreaterEqual(metrics["hit_ratio"], 0.0)
        self.assertIn("risk_on", metrics["regime_conditional_performance"])
        self.assertEqual(metrics["melao_index_placeholder"]["status"], "placeholder")


if __name__ == "__main__":
    unittest.main()
