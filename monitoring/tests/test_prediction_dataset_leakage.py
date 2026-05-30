"""Tests for prediction dataset leakage controls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase


class PredictionDatasetLeakageTests(SimpleTestCase):
    """Feature availability timestamps prevent future leakage."""

    def test_future_feature_is_rejected(self) -> None:
        """Features available after the prediction time cannot be used."""
        from sourceflow.finance_dataset.leakage import assert_no_lookahead

        target_time = datetime(2026, 1, 10, tzinfo=UTC)
        rows = [
            {
                "symbol": "AAPL",
                "timestamp": target_time,
                "available_at": target_time + timedelta(days=1),
                "feature_name": "future_fact",
            }
        ]

        with self.assertRaisesRegex(ValueError, "future_fact"):
            assert_no_lookahead(rows)

    def test_fundamental_filed_at_controls_availability(self) -> None:
        """Fundamental facts use filed_at rather than fiscal end date."""
        from sourceflow.finance_dataset.leakage import fundamental_available_at

        row = {
            "end_date": "2025-12-31",
            "filed_at": "2026-02-01T12:00:00+00:00",
        }

        self.assertEqual(
            fundamental_available_at(row),
            datetime(2026, 2, 1, 12, 0, tzinfo=UTC),
        )
