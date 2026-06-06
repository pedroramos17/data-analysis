"""Tests for Phase 6 sliding-window dataset builder."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.config.settings import load_runtime_settings
from src.pipeline.windows import (
    WindowSpec,
    build_dataset,
    diagnose_all_windows,
    diagnose_window,
    inspect_dataset,
    purge_overlap,
    split_windows,
)
from src.pipeline.windows.embargo import (
    apply_embargo,
    check_embargo_violation,
    embargo_range,
    purge_overlap as embargo_purge_overlap,
)
from src.pipeline.windows.purged_cv import purged_kfold_split, purged_kfold_windows
from src.providers.registry import ProviderRegistry, build_provider_registry


class TestEmbargo(unittest.TestCase):
    """Unit tests for embargo and purge logic."""

    def test_embargo_range_extends_end(self) -> None:
        start = datetime(2020, 1, 1, tzinfo=UTC)
        end = datetime(2020, 1, 10, tzinfo=UTC)
        embargo = timedelta(days=5)
        result_start, result_end = embargo_range(start, end, embargo)
        self.assertEqual(result_start, start)
        self.assertEqual(result_end, datetime(2020, 1, 15, tzinfo=UTC))

    def test_purge_overlap_truncates_train(self) -> None:
        train_start = datetime(2020, 1, 1, tzinfo=UTC)
        train_end = datetime(2020, 6, 30, tzinfo=UTC)
        test_start = datetime(2020, 6, 15, tzinfo=UTC)
        test_end = datetime(2020, 7, 15, tzinfo=UTC)
        new_end = purge_overlap(train_start, train_end, test_start, test_end)
        self.assertLess(new_end, test_start)

    def test_purge_overlap_no_overlap_unchanged(self) -> None:
        train_start = datetime(2020, 1, 1, tzinfo=UTC)
        train_end = datetime(2020, 3, 31, tzinfo=UTC)
        test_start = datetime(2020, 4, 1, tzinfo=UTC)
        test_end = datetime(2020, 6, 30, tzinfo=UTC)
        new_end = purge_overlap(train_start, train_end, test_start, test_end)
        self.assertEqual(new_end, train_end)

    def test_check_embargo_violation_true(self) -> None:
        train_latest = datetime(2020, 1, 10, tzinfo=UTC)
        test_earliest = datetime(2020, 1, 12, tzinfo=UTC)
        embargo = timedelta(days=5)
        self.assertTrue(check_embargo_violation(train_latest, test_earliest, embargo))

    def test_check_embargo_violation_false(self) -> None:
        train_latest = datetime(2020, 1, 1, tzinfo=UTC)
        test_earliest = datetime(2020, 1, 10, tzinfo=UTC)
        embargo = timedelta(days=5)
        self.assertFalse(check_embargo_violation(train_latest, test_earliest, embargo))

    def test_apply_embargo_filters(self) -> None:
        timestamps = [
            datetime(2020, 1, 1, tzinfo=UTC),
            datetime(2020, 1, 5, tzinfo=UTC),
            datetime(2020, 1, 10, tzinfo=UTC),
            datetime(2020, 1, 15, tzinfo=UTC),
        ]
        cutoff = datetime(2020, 1, 12, tzinfo=UTC)
        embargo = timedelta(days=5)
        filtered = apply_embargo(timestamps, cutoff, embargo)
        # boundary = cutoff - embargo = Jan 7; keep timestamps <= Jan 7
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0], datetime(2020, 1, 1, tzinfo=UTC))
        self.assertEqual(filtered[1], datetime(2020, 1, 5, tzinfo=UTC))


class TestSplitterModes(unittest.TestCase):
    """Unit tests for split_windows in all modes."""

    def _make_rows(self, start: datetime, days: int, symbol: str = "SPY") -> list[dict[str, object]]:
        return [
            {"symbol": symbol, "ts": (start + timedelta(days=i)).isoformat(), "close": float(i)}
            for i in range(days)
        ]

    def test_rolling_window_basic(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 1000)
        config = {
            "mode": "rolling",
            "train_size_days": 180,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
        }
        windows = split_windows(rows, config)
        self.assertGreater(len(windows), 0)
        for w in windows:
            self.assertLessEqual(w.train_end, w.validation_start)
            self.assertLessEqual(w.validation_end, w.test_start)
            self.assertEqual(w.mode, "rolling")

    def test_expanding_window_grows(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 1000)
        config = {
            "mode": "expanding",
            "train_size_days": 180,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
        }
        windows = split_windows(rows, config)
        self.assertGreater(len(windows), 0)
        # Expanding: train_start should be same for all
        train_starts = [w.train_start for w in windows]
        self.assertEqual(len(set(train_starts)), 1)
        # train_end should increase
        train_ends = [w.train_end for w in windows]
        self.assertEqual(train_ends, sorted(train_ends))

    def test_anchored_window(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 1000)
        config = {
            "mode": "anchored",
            "train_size_days": 180,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
        }
        windows = split_windows(rows, config)
        self.assertGreater(len(windows), 0)
        for w in windows:
            self.assertEqual(w.mode, "anchored")

    def test_purged_window(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 1000)
        config = {
            "mode": "purged",
            "train_size_days": 180,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
        }
        windows = split_windows(rows, config)
        self.assertGreater(len(windows), 0)
        for w in windows:
            self.assertEqual(w.mode, "purged")
            # With purge, train_end must be strictly before validation_start
            self.assertLess(w.train_end, w.validation_start)

    def test_embargoed_cv(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 1000)
        config = {
            "mode": "embargoed_cv",
            "n_splits": 5,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
        }
        windows = split_windows(rows, config)
        # Fold 0 is skipped because there's no data before the first test block
        # to train on (train_end would be before global_start).
        self.assertGreaterEqual(len(windows), 3)
        self.assertLessEqual(len(windows), 5)
        for w in windows:
            self.assertEqual(w.mode, "embargoed_cv")

    def test_no_future_leakage(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 500)
        config = {
            "mode": "rolling",
            "train_size_days": 100,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
        }
        windows = split_windows(rows, config)
        for w in windows:
            # No train row should be >= test_start
            self.assertLess(w.train_end, w.test_start)

    def test_empty_rows_returns_empty(self) -> None:
        self.assertEqual(split_windows([], {"mode": "rolling"}), [])

    def test_insufficient_data_returns_empty(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 10)
        config = {
            "mode": "rolling",
            "train_size_days": 100,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 1000,
        }
        windows = split_windows(rows, config)
        self.assertEqual(len(windows), 0)


class TestPurgedCV(unittest.TestCase):
    """Tests for purged K-fold cross-validation."""

    def _make_rows(self, start: datetime, days: int, symbol: str = "SPY") -> list[dict[str, object]]:
        return [
            {"symbol": symbol, "ts": (start + timedelta(days=i)).isoformat(), "close": float(i)}
            for i in range(days)
        ]

    def test_purged_kfold_split(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 500)
        folds = purged_kfold_split(rows, n_splits=5, embargo_days=5, horizon_days=5)
        self.assertEqual(len(folds), 5)
        for fold in folds:
            # No train index should be in test indices
            self.assertEqual(set(fold.train_indices) & set(fold.test_indices), set())
            self.assertGreater(len(fold.test_indices), 0)
        # Fold 0 may have 0 train indices because test starts at global_start
        self.assertGreater(len(folds[1].train_indices), 0)

    def test_purged_kfold_windows(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 500)
        config = {"n_splits": 5, "embargo_days": 5, "horizon_days": 5, "min_samples_per_window": 10}
        windows = purged_kfold_windows(rows, config)
        self.assertEqual(len(windows), 5)
        for w in windows:
            self.assertEqual(w.mode, "embargoed_cv")


class TestDiagnostics(unittest.TestCase):
    """Tests for window diagnostics."""

    def _make_rows(self, start: datetime, days: int, symbol: str = "SPY") -> list[dict[str, object]]:
        return [
            {"symbol": symbol, "ts": (start + timedelta(days=i)).isoformat(), "close": float(i)}
            for i in range(days)
        ]

    def test_diagnose_window_no_leakage(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 500)
        config = {
            "mode": "rolling",
            "train_size_days": 100,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
        }
        windows = split_windows(rows, config)
        self.assertGreater(len(windows), 0)
        diag = diagnose_window(windows[0], rows)
        self.assertEqual(diag.future_leakage_violations, 0)
        self.assertTrue(diag.horizon_compliant)
        self.assertEqual(diag.embargo_violations, 0)

    def test_diagnose_all_windows(self) -> None:
        rows = self._make_rows(datetime(2020, 1, 1, tzinfo=UTC), 500)
        config = {
            "mode": "rolling",
            "train_size_days": 100,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
        }
        windows = split_windows(rows, config)
        diags = diagnose_all_windows(windows, rows)
        self.assertEqual(len(diags), len(windows))
        for d in diags:
            self.assertEqual(d.future_leakage_violations, 0)
            self.assertTrue(d.horizon_compliant)


class TestDatasetBuilder(unittest.TestCase):
    """Integration tests for dataset builder."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.lake_root = Path(self.tmpdir) / "lake"
        self.lake_root.mkdir(parents=True, exist_ok=True)
        self.output_root = self.lake_root / "datasets"
        # Write simple mock data as fallback JSONL
        self._write_mock_data()
        self.registry = build_provider_registry(load_runtime_settings())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_mock_data(self) -> None:
        rows = [
            {"symbol": "SPY", "ts": (datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat(), "close": float(i)}
            for i in range(365)
        ]
        # Also add 2021 data
        rows.extend([
            {"symbol": "SPY", "ts": (datetime(2021, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat(), "close": float(365 + i)}
            for i in range(365)
        ])
        # Write as fallback JSONL (no pyarrow required)
        from src.pipeline.ingestion.validators import rows_to_parquet_bytes
        data = rows_to_parquet_bytes(rows)
        silver_dir = self.lake_root / "silver" / "market_bars"
        silver_dir.mkdir(parents=True, exist_ok=True)
        (silver_dir / "part-000.parquet").write_bytes(data)

    def test_build_dataset_rolling(self) -> None:
        config = {
            "dataset_name": "test_rolling",
            "version": "phase6_test",
            "input_path": str(self.lake_root / "silver" / "market_bars"),
            "lake_root": str(self.lake_root),
            "output_root": str(self.output_root),
            "mode": "rolling",
            "train_size_days": 180,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 60,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
            "require_duckdb": False,
        }
        result = build_dataset(config, self.registry)
        self.assertEqual(result.status, "COMPLETED")
        self.assertGreater(result.windows, 0)
        self.assertTrue(result.overall_leakage_passed)
        for out in result.outputs:
            self.assertGreater(out.train_rows, 0)
            self.assertGreaterEqual(out.validation_rows, 0)
            self.assertGreater(out.test_rows, 0)

    def test_build_dataset_accepts_nested_sliding_window_config(self) -> None:
        config = {
            "dataset_name": "test_nested",
            "version": "phase6_test",
            "input_path": str(self.lake_root / "silver" / "market_bars"),
            "lake_root": str(self.lake_root),
            "output_root": str(self.output_root),
            "sliding_window": {
                "mode": "rolling",
                "train_size_days": 180,
                "validation_size_days": 30,
                "test_size_days": 30,
                "step_size_days": 60,
                "embargo_days": 5,
                "horizon_days": 5,
                "min_samples_per_window": 10,
            },
            "require_duckdb": False,
        }
        result = build_dataset(config, self.registry)
        self.assertEqual(result.status, "COMPLETED")
        self.assertGreater(result.windows, 0)

    def test_inspect_dataset(self) -> None:
        config = {
            "dataset_name": "test_inspect",
            "version": "phase6_test",
            "input_path": str(self.lake_root / "silver" / "market_bars"),
            "lake_root": str(self.lake_root),
            "output_root": str(self.output_root),
            "mode": "rolling",
            "train_size_days": 180,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 60,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
            "require_duckdb": False,
        }
        build_dataset(config, self.registry)
        info = inspect_dataset("test_inspect", self.output_root)
        self.assertEqual(info["status"], "FOUND")
        self.assertGreater(info["windows_found"], 0)

    def test_reproducibility(self) -> None:
        """Same config + same input must produce identical windows."""
        config = {
            "dataset_name": "test_repro",
            "version": "phase6_test",
            "input_path": str(self.lake_root / "silver" / "market_bars"),
            "lake_root": str(self.lake_root),
            "output_root": str(self.output_root),
            "mode": "rolling",
            "train_size_days": 180,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 60,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
            "require_duckdb": False,
        }
        result1 = build_dataset(config, self.registry)
        result2 = build_dataset(config, self.registry)
        self.assertEqual(result1.windows, result2.windows)
        for o1, o2 in zip(result1.outputs, result2.outputs):
            self.assertEqual(o1.window_id, o2.window_id)
            self.assertEqual(o1.train_rows, o2.train_rows)
            self.assertEqual(o1.validation_rows, o2.validation_rows)
            self.assertEqual(o1.test_rows, o2.test_rows)
            self.assertEqual(o1.content_hash, o2.content_hash)

    def test_no_windows_for_too_short_data(self) -> None:
        # Write very short data
        rows = [
            {"symbol": "SPY", "ts": "2020-01-01T00:00:00+00:00", "close": 100.0},
            {"symbol": "SPY", "ts": "2020-01-02T00:00:00+00:00", "close": 101.0},
        ]
        from src.pipeline.ingestion.validators import rows_to_parquet_bytes
        data = rows_to_parquet_bytes(rows)
        short_dir = self.lake_root / "short"
        short_dir.mkdir(parents=True, exist_ok=True)
        (short_dir / "part-000.parquet").write_bytes(data)
        config = {
            "dataset_name": "test_short",
            "version": "phase6_test",
            "input_path": str(short_dir),
            "lake_root": str(self.lake_root),
            "output_root": str(self.output_root),
            "mode": "rolling",
            "train_size_days": 100,
            "validation_size_days": 30,
            "test_size_days": 30,
            "step_size_days": 30,
            "embargo_days": 5,
            "horizon_days": 5,
            "min_samples_per_window": 10,
            "require_duckdb": False,
        }
        result = build_dataset(config, self.registry)
        self.assertEqual(result.status, "NO_WINDOWS")
        self.assertEqual(result.windows, 0)


if __name__ == "__main__":
    unittest.main()
