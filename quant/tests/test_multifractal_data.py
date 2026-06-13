"""Quant multifractal Phase 1 data contract tests."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase


class QuantMultifractalDataContractTests(TestCase):
    """Canonical bars, returns, and registry metadata should be deterministic."""

    def test_csv_to_parquet_roundtrip(self) -> None:
        """CSV import writes and reads partitioned OHLCV Parquet bars."""
        from quant.services.multifractal.data.parquet_store import (
            read_bars_parquet,
            write_bars_parquet,
        )
        from quant.services.multifractal.data.validators import import_ohlcv_csv

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "spy.csv"
            _write_csv(csv_path, _valid_csv_rows())
            bars = import_ohlcv_csv(csv_path, "SPY", "stock", "1d", "unit-test")
            write_result = write_bars_parquet(bars, Path(temp_dir) / "bars")
            loaded = read_bars_parquet(write_result.root_path, symbol="SPY")

        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0].symbol, "SPY")
        self.assertEqual(loaded[0].asset_class, "stock")
        self.assertEqual(loaded[-1].close, 102.0)
        self.assertIn("asset_class=stock", write_result.partition_paths[0])

    def test_bad_timestamp_handling(self) -> None:
        """Bad timestamp values fail with the offending value."""
        from quant.services.multifractal.data.validators import import_ohlcv_csv

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "bad.csv"
            rows = _valid_csv_rows()
            rows[0]["timestamp"] = "not-a-date"
            _write_csv(csv_path, rows)

            with self.assertRaisesRegex(ValueError, "not-a-date"):
                import_ohlcv_csv(csv_path, "SPY", "stock", "1d", "unit-test")

    def test_missing_price_handling(self) -> None:
        """Missing required price fields are rejected before storage."""
        from quant.services.multifractal.data.validators import import_ohlcv_csv

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "missing.csv"
            rows = _valid_csv_rows()
            rows[1]["close"] = ""
            _write_csv(csv_path, rows)

            with self.assertRaisesRegex(ValueError, "close"):
                import_ohlcv_csv(csv_path, "SPY", "stock", "1d", "unit-test")

    def test_duplicate_timestamp_detection(self) -> None:
        """Duplicate symbol/timeframe timestamps are rejected."""
        from quant.services.multifractal.data.validators import import_ohlcv_csv

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "dupes.csv"
            rows = _valid_csv_rows()
            rows[2]["timestamp"] = rows[1]["timestamp"]
            _write_csv(csv_path, rows)

            with self.assertRaisesRegex(ValueError, "duplicate timestamp"):
                import_ohlcv_csv(csv_path, "SPY", "stock", "1d", "unit-test")

    def test_non_monotonic_timestamp_detection(self) -> None:
        """Non-monotonic input rows are rejected before sorting."""
        from quant.services.multifractal.data.validators import import_ohlcv_csv

        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "non_monotonic.csv"
            rows = _valid_csv_rows()
            rows[1], rows[2] = rows[2], rows[1]
            _write_csv(csv_path, rows)

            with self.assertRaisesRegex(ValueError, "timestamp order"):
                import_ohlcv_csv(csv_path, "SPY", "stock", "1d", "unit-test")

    def test_returns_generation_correctness(self) -> None:
        """Derived returns use close prices without lookahead."""
        from quant.services.multifractal.data.validators import (
            generate_return_records,
        )

        returns = generate_return_records(_bar_records(), price_col="close")

        self.assertEqual(len(returns), 2)
        self.assertEqual(returns[0].timestamp, _ts("2024-01-02T00:00:00Z"))
        self.assertAlmostEqual(returns[0].simple_return, 0.01)
        self.assertAlmostEqual(returns[0].log_return, 0.00995033085)
        self.assertAlmostEqual(returns[1].squared_return, returns[1].log_return**2)

    def test_registry_dataset_id_is_deterministic(self) -> None:
        """The SQLite-backed registry stores stable dataset identifiers."""
        from quant.models import MarketDataset
        from quant.services.multifractal.data.sqlite_registry import (
            build_dataset_id,
            register_multifractal_dataset,
        )

        metadata = {
            "kind": "bars",
            "symbols": ["SPY"],
            "source": "unit-test",
            "timeframe": "1d",
            "schema_version": "ohlcv-b1",
        }

        left = build_dataset_id(metadata)
        right = build_dataset_id(dict(reversed(list(metadata.items()))))
        dataset = register_multifractal_dataset(
            dataset_id=left,
            kind="bars",
            artifact_root="data/quant_multifractal/bars",
            metadata=metadata,
            row_count=3,
        )

        self.assertEqual(left, right)
        self.assertEqual(dataset.metadata_json["dataset_id"], left)
        self.assertEqual(MarketDataset.objects.count(), 1)


def _valid_csv_rows() -> list[dict[str, str]]:
    return [
        _csv_row("2024-01-01T00:00:00Z", "100", "101", "99", "100"),
        _csv_row("2024-01-02T00:00:00Z", "100", "102", "100", "101"),
        _csv_row("2024-01-03T00:00:00Z", "101", "103", "100", "102"),
    ]


def _csv_row(
    timestamp: str,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
) -> dict[str, str]:
    return {
        "timestamp": timestamp,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": "1000",
        "exchange": "ARCX",
        "currency": "USD",
        "adjusted_close": close_price,
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _bar_records() -> list[object]:
    from sourceflow.finance_core import BarRecord

    return [
        BarRecord(
            symbol="SPY",
            asset_class="stock",
            exchange="ARCX",
            timestamp=_ts("2024-01-01T00:00:00Z"),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
            currency="USD",
            source="unit",
            timeframe="1d",
            adjusted_close=100,
        ),
        BarRecord(
            symbol="SPY",
            asset_class="stock",
            exchange="ARCX",
            timestamp=_ts("2024-01-02T00:00:00Z"),
            open=100,
            high=102,
            low=99,
            close=101,
            volume=1000,
            currency="USD",
            source="unit",
            timeframe="1d",
            adjusted_close=101,
        ),
        BarRecord(
            symbol="SPY",
            asset_class="stock",
            exchange="ARCX",
            timestamp=_ts("2024-01-03T00:00:00Z"),
            open=101,
            high=103,
            low=100,
            close=102,
            volume=1000,
            currency="USD",
            source="unit",
            timeframe="1d",
            adjusted_close=102,
        ),
    ]


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
