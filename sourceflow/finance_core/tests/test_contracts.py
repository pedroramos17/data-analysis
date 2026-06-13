"""Pure contract tests for finance_core."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sourceflow.finance_core import (
    BarRecord,
    CompanyRelation,
    InstrumentRef,
    LimitOrderBookSnapshot,
    MarketBarPoint,
    OrderBookLevel,
    bar_to_row,
    row_to_bar,
)
from sourceflow.finance_core.ids import stable_id
from sourceflow.finance_core.time import require_datetime


class FinanceCoreContractTests(unittest.TestCase):
    def test_bar_record_roundtrip_preserves_canonical_fields(self) -> None:
        timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
        bar = BarRecord(
            symbol="SPY",
            timestamp=timestamp,
            timeframe="1d",
            open=100,
            high=101,
            low=99,
            close=100.5,
            volume=1000,
            asset_class="equity",
            exchange="ARCX",
            currency="USD",
            source="unit",
        )

        restored = row_to_bar(bar_to_row(bar))

        self.assertEqual(restored.symbol, "SPY")
        self.assertEqual(restored.timestamp, timestamp)
        self.assertEqual(restored.asset_class, "equity")
        self.assertEqual(restored.close, 100.5)

    def test_market_contracts_live_in_finance_core(self) -> None:
        instrument = InstrumentRef("SPY", "ARCX", asset_class="equity")
        snapshot = LimitOrderBookSnapshot(
            instrument=instrument,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            bids=[OrderBookLevel(100, 10)],
            asks=[OrderBookLevel(101, 11)],
        )
        bar = MarketBarPoint(instrument, snapshot.timestamp, "1d", close=100.5)
        relation = CompanyRelation("SPY", "QQQ", "correlates_with", weight=0.8)

        self.assertEqual(snapshot.bids[0].price, 100)
        self.assertEqual(bar.instrument.symbol, "SPY")
        self.assertEqual(relation.target_symbol, "QQQ")

    def test_require_datetime_normalizes_naive_values(self) -> None:
        normalized = require_datetime(datetime(2024, 1, 1), "as_of")

        self.assertEqual(normalized.tzinfo, timezone.utc)

    def test_stable_id_is_ordered_and_deterministic(self) -> None:
        left = stable_id("SPY", "1d", "close", prefix="dataset")
        right = stable_id("SPY", "1d", "close", prefix="dataset")
        different = stable_id("close", "1d", "SPY", prefix="dataset")

        self.assertEqual(left, right)
        self.assertTrue(left.startswith("dataset_"))
        self.assertNotEqual(left, different)


if __name__ == "__main__":
    unittest.main()
