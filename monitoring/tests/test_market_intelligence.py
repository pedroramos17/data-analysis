"""Tests for Sourceflow market intelligence primitives and imports."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from monitoring.models import MarketInstrument, MarketTick
from sourceflow.intelligence.market.contracts import (
    CompanyRelation,
    InstrumentRef,
    LimitOrderBookSnapshot,
    MarketBarPoint,
    OrderBookLevel,
)
from sourceflow.intelligence.market.features import build_bar_features
from sourceflow.intelligence.market.io import (
    build_market_intelligence_frame,
    write_jsonl_market_snapshot,
)
from sourceflow.intelligence.market.knowledge_graph import (
    build_company_graph,
    graph_exposure_scores,
    neighbor_symbols,
)
from sourceflow.intelligence.market.microstructure import (
    dollar_volume,
    microprice,
    mid_price,
    order_book_imbalance,
    spread_abs,
)
from sourceflow.intelligence.market.policy import (
    validate_authorized_vendor_config,
    validate_ingestion_mode,
)


class MarketIntelligenceTests(TestCase):
    """Regression tests for compliant market intelligence behavior."""

    def test_forbidden_modes_are_rejected(self) -> None:
        """Policy and command reject bypass/evasion labels before parsing."""
        with self.assertRaisesRegex(ValueError, "bypass_login"):
            validate_ingestion_mode("bypass_login")
        with self.assertRaises(CommandError):
            call_command(
                "import_market_snapshot",
                path="missing.jsonl",
                mode="bypass_login",
                dry_run=True,
            )

    def test_authorized_vendor_config_validates_required_shape(self) -> None:
        """Vendor browser mode requires local authorization metadata."""
        config = {
            "vendor": "TradingView",
            "authorization_basis": "vendor agreement",
            "storage_state_path": "state.json",
            "capture_url": "https://example.com/export.jsonl",
        }

        validate_authorized_vendor_config(config, "vendor_authorized_browser")

        with self.assertRaisesRegex(ValueError, "storage_state_path"):
            validate_authorized_vendor_config(
                {"vendor": "TradingView", "authorization_basis": "agreement"},
                "vendor_authorized_browser",
            )

    def test_dollar_volume_computed(self) -> None:
        """Dollar volume works directly and through bar feature rows."""
        instrument = InstrumentRef("AAPL", "NASDAQ")
        bar = MarketBarPoint(
            instrument=instrument,
            timestamp=_timestamp(),
            timeframe="1m",
            close=5,
            volume=4,
        )

        rows = build_bar_features([bar])

        self.assertEqual(dollar_volume(5, 4), 20)
        self.assertEqual(rows[0]["dollar_volume"], 20)

    def test_spread_mid_microprice_and_imbalance(self) -> None:
        """Microstructure functions handle valid and empty books safely."""
        snapshot = _lob_snapshot()
        empty_snapshot = LimitOrderBookSnapshot(
            instrument=InstrumentRef("EMPTY", "TEST"),
            timestamp=_timestamp(),
            bids=[],
            asks=[],
        )

        self.assertEqual(mid_price(100, 102), 101)
        self.assertEqual(spread_abs(100, 102), 2)
        self.assertAlmostEqual(microprice(snapshot), 101.6)
        self.assertAlmostEqual(order_book_imbalance(snapshot), 0.6)
        self.assertIsNone(microprice(empty_snapshot))
        self.assertEqual(order_book_imbalance(empty_snapshot), 0)

    def test_graph_propagation_over_company_edges(self) -> None:
        """Supplier and banking relation weights propagate seed exposure."""
        instruments = [
            InstrumentRef("SUP", "NYSE"),
            InstrumentRef("BANK", "NYSE"),
            InstrumentRef("CUST", "NASDAQ"),
        ]
        relations = [
            CompanyRelation("SUP", "CUST", "supplier", 0.5),
            CompanyRelation("BANK", "CUST", "lender", 0.4),
        ]

        graph = build_company_graph(instruments, relations)
        scores = graph_exposure_scores(
            graph, {"SUP": 1.0, "BANK": 0.5}, decay=1, steps=1
        )

        self.assertEqual(neighbor_symbols(graph, "SUP", {"supplier"}), ["CUST"])
        self.assertAlmostEqual(scores["CUST"], 0.7)

    def test_jsonl_snapshot_builds_prediction_frame(self) -> None:
        """Mixed JSONL snapshots become feature rows with KG exposure."""
        with TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "snapshot.jsonl"
            write_jsonl_market_snapshot(snapshot_path, _snapshot_records())

            rows = build_market_intelligence_frame(snapshot_path)

        row_types = {row["record_type"] for row in rows}
        tick_row = _first_row(rows, "tick_feature")

        self.assertIn("bar_feature", row_types)
        self.assertIn("lob_feature", row_types)
        self.assertIn("open_order_flow_feature", row_types)
        self.assertEqual(tick_row["mid_price"], 101)
        self.assertEqual(tick_row["graph_exposure_score"], 1.0)

    def test_command_dry_run_parses_without_database_writes(self) -> None:
        """Dry-run reports record counts and does not persist market rows."""
        with TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "snapshot.jsonl"
            write_jsonl_market_snapshot(snapshot_path, _snapshot_records())
            output = StringIO()

            call_command(
                "import_market_snapshot",
                path=str(snapshot_path),
                mode="local_jsonl",
                dry_run=True,
                stdout=output,
            )

        self.assertIn("bar=1", output.getvalue())
        self.assertEqual(MarketInstrument.objects.count(), 0)
        self.assertEqual(MarketTick.objects.count(), 0)


def _timestamp() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def _lob_snapshot() -> LimitOrderBookSnapshot:
    return LimitOrderBookSnapshot(
        instrument=InstrumentRef("AAPL", "NASDAQ"),
        timestamp=_timestamp(),
        bids=[OrderBookLevel(price=100, size=8)],
        asks=[OrderBookLevel(price=102, size=2)],
    )


def _snapshot_records() -> list[dict[str, object]]:
    return [
        _instrument_record(),
        _tick_record(),
        _bar_record(),
        _lob_record(),
        _flow_record(),
        _relation_record(),
        _knowledge_signal_record(),
    ]


def _instrument_record() -> dict[str, object]:
    return {
        "record_type": "instrument",
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "industry": "Hardware",
    }


def _tick_record() -> dict[str, object]:
    return {
        "record_type": "tick",
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "timestamp": "2026-01-01T00:00:00Z",
        "price": 101,
        "bid": 100,
        "ask": 102,
        "volume": 5,
        "source": "licensed-feed",
    }


def _bar_record() -> dict[str, object]:
    return {
        "record_type": "bar",
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "timestamp": "2026-01-01T00:01:00Z",
        "timeframe": "1m",
        "close": 101,
        "volume": 10,
        "source": "licensed-feed",
    }


def _lob_record() -> dict[str, object]:
    return {
        "record_type": "lob",
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "timestamp": "2026-01-01T00:00:00Z",
        "bids": [{"price": 100, "size": 8}],
        "asks": [{"price": 102, "size": 2}],
    }


def _flow_record() -> dict[str, object]:
    return {
        "record_type": "open_order_flow",
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "timestamp": "2026-01-01T00:00:00Z",
        "submitted_buy_volume": 12,
        "submitted_sell_volume": 3,
    }


def _relation_record() -> dict[str, object]:
    return {
        "record_type": "relation",
        "source_symbol": "AAPL",
        "target_symbol": "MSFT",
        "relation_type": "competitor",
        "weight": 0.5,
    }


def _knowledge_signal_record() -> dict[str, object]:
    return {"record_type": "knowledge_signal", "symbol": "AAPL", "score": 1.0}


def _first_row(
    rows: list[dict[str, object]],
    record_type: str,
) -> dict[str, object]:
    for row in rows:
        if row["record_type"] == record_type:
            return row
    raise AssertionError(f"Missing row {record_type}; expected feature row")
