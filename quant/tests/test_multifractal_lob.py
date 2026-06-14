"""Quant multifractal Phase 11 LOB readiness tests."""

from __future__ import annotations

from django.test import SimpleTestCase

from quant.services.lob.parser import LOBSnapshot


class QuantMultifractalLOBTests(SimpleTestCase):
    """LOB multifractal transforms should work on synthetic snapshots."""

    def test_lob_feature_placeholders_use_observed_book_only(self) -> None:
        """Spread and imbalance rows come from same-timestamp book state."""
        from quant.services.multifractal.lob.features import build_lob_mf_features

        rows = build_lob_mf_features(_synthetic_lob(32))

        self.assertEqual(rows[0]["source_timestamp"], "2026-01-01T00:00:00")
        self.assertIn("spread", rows[0])
        self.assertIn("order_imbalance", rows[0])

    def test_mfdfa_runs_on_spread_and_imbalance(self) -> None:
        """MF-DFA summaries are available for spread and imbalance series."""
        from quant.services.multifractal.lob.multifractal_lob import (
            analyze_lob_multifractality,
        )

        report = analyze_lob_multifractality(_synthetic_lob(48))

        self.assertIn("spread_mfdfa", report)
        self.assertIn("imbalance_mfdfa", report)
        self.assertGreaterEqual(report["spread_mfdfa"]["valid_scale_count"], 1)

    def test_partition_function_runs_on_event_durations(self) -> None:
        """Positive inter-event durations feed the partition baseline."""
        from quant.services.multifractal.lob.multifractal_lob import (
            analyze_lob_multifractality,
        )

        report = analyze_lob_multifractality(_synthetic_lob(48))

        self.assertEqual(
            report["duration_partition"]["method"],
            "partition_function",
        )

    def test_buy_sell_mfdcca_summary_is_reported(self) -> None:
        """Buy/sell depth series are aligned for MF-DCCA diagnostics."""
        from quant.services.multifractal.lob.multifractal_lob import (
            analyze_lob_multifractality,
        )

        report = analyze_lob_multifractality(_synthetic_lob(48))

        self.assertIn("cross_correlation_mean", report["buy_sell_mfdcca"])


def _synthetic_lob(length: int) -> list[LOBSnapshot]:
    rows: list[LOBSnapshot] = []
    for index in range(length):
        mid = 100.0 + index * 0.01
        spread = 0.02 + (index % 5) * 0.001
        rows.append(_snapshot(index, mid, spread))
    return rows


def _snapshot(index: int, mid: float, spread: float) -> LOBSnapshot:
    timestamp = f"2026-01-01T00:00:{index:02d}"
    bid = mid - spread / 2.0
    ask = mid + spread / 2.0
    return LOBSnapshot(
        timestamp=timestamp,
        symbol="BTCUSD",
        bids=((bid, 10.0 + index), (bid - 0.01, 8.0)),
        asks=((ask, 9.0), (ask + 0.01, 7.0 + index * 0.5)),
        venue_type="crypto",
        metadata={"event_type": "book"},
    )
