"""Tests for CFTC Commitments of Traders normalization."""

from __future__ import annotations

from django.test import SimpleTestCase


class CftcCotNormalizationTests(SimpleTestCase):
    """CFTC rows become numeric commitment records."""

    def test_numeric_columns_are_normalized(self) -> None:
        """Comma-formatted COT values are converted to floats."""
        from sourceflow.finance_ingestion.connectors.cftc_cot import normalize_cot_rows

        rows = normalize_cot_rows(
            [
                {
                    "Market_and_Exchange_Names": "GOLD - COMMODITY EXCHANGE INC.",
                    "CFTC_Contract_Market_Code": "088691",
                    "Report_Date_as_YYYY-MM-DD": "2026-01-06",
                    "Open_Interest_All": "1,234",
                    "M_Money_Positions_Long_All": "500",
                    "M_Money_Positions_Short_All": "120",
                }
            ],
            "futures_options",
        )

        self.assertEqual(rows[0]["market_name"], "GOLD - COMMODITY EXCHANGE INC.")
        self.assertEqual(rows[0]["report_type"], "futures_options")
        self.assertEqual(rows[0]["managed_money_long"], 500.0)
        self.assertEqual(rows[0]["open_interest"], 1234.0)
