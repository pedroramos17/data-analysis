"""Tests for SEC EDGAR XBRL normalization."""

from __future__ import annotations

from django.test import SimpleTestCase


class SecEdgarNormalizationTests(SimpleTestCase):
    """Companyfacts payloads become fundamental fact rows."""

    def test_companyfacts_are_flattened_with_filing_metadata(self) -> None:
        """Quarterly facts preserve accession, form, fiscal period, and filed date."""
        from sourceflow.finance_ingestion.connectors.sec_edgar import (
            normalize_companyfacts,
        )

        rows = normalize_companyfacts("0000320193", _companyfacts_payload(), {"10-Q"})

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cik"], "0000320193")
        self.assertEqual(rows[0]["taxonomy"], "us-gaap")
        self.assertEqual(rows[0]["tag"], "Revenues")
        self.assertEqual(rows[0]["form_type"], "10-Q")
        self.assertEqual(rows[0]["fiscal_period"], "Q1")
        self.assertEqual(rows[0]["accession_number"], "0000320193-26-000001")
        self.assertEqual(rows[0]["value"], 1000.0)


def _companyfacts_payload() -> dict[str, object]:
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-02-01",
                                "end": "2025-12-31",
                                "start": "2025-10-01",
                                "accn": "0000320193-26-000001",
                                "val": 1000,
                            },
                            {"fy": 2025, "fp": "FY", "form": "10-K", "val": 900},
                        ]
                    }
                }
            }
        }
    }
