"""Tests for FRED observation normalization."""

from __future__ import annotations

from django.test import SimpleTestCase


class FredNormalizationTests(SimpleTestCase):
    """FRED payloads become macro observation rows."""

    def test_observations_skip_missing_values(self) -> None:
        """FRED missing-value markers are omitted from normalized rows."""
        from sourceflow.finance_ingestion.connectors.fred import normalize_observations

        rows = normalize_observations(
            "GDP",
            {
                "observations": [
                    {
                        "date": "2026-01-01",
                        "value": "22000.5",
                        "realtime_start": "2026-01-31",
                        "realtime_end": "2026-02-28",
                    },
                    {"date": "2026-04-01", "value": "."},
                ]
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["series_id"], "GDP")
        self.assertEqual(rows[0]["value"], 22000.5)
        self.assertEqual(rows[0]["realtime_start"], "2026-01-31")
