"""Purged K-fold cross-validation for time-series."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta

from src.pipeline.windows.embargo import embargo_range, purge_overlap
from src.pipeline.windows.splitter import WindowSpec, _count_samples, _parse_ts


@dataclass(frozen=True, slots=True)
class PurgedFoldResult:
    """Result of one purged fold."""

    fold_index: int
    train_indices: list[int]
    test_indices: list[int]
    purged_count: int
    embargo_days: int

    def to_dict(self) -> dict[str, object]:
        return {
            "fold_index": self.fold_index,
            "train_samples": len(self.train_indices),
            "test_samples": len(self.test_indices),
            "purged_count": self.purged_count,
            "embargo_days": self.embargo_days,
        }


def purged_kfold_split(
    rows: Sequence[Mapping[str, object]],
    n_splits: int = 5,
    embargo_days: int = 5,
    horizon_days: int = 5,
    purge: bool = True,
) -> list[PurgedFoldResult]:
    """Generate purged K-fold splits for time-series data.

    Each fold uses one contiguous temporal block as test and all earlier
    blocks as train. Overlapping observations are purged from train to
    prevent leakage.
    """
    timestamps = sorted(
        (_parse_ts(row.get("ts")), idx)
        for idx, row in enumerate(rows)
        if _parse_ts(row.get("ts")) is not None
    )
    if not timestamps:
        return []

    ts_list = [ts for ts, _ in timestamps]
    global_start = ts_list[0]
    global_end = ts_list[-1]
    embargo_delta = timedelta(days=embargo_days)
    horizon_delta = timedelta(days=horizon_days)

    total_span = global_end - global_start - horizon_delta
    if total_span.days <= 0:
        return []

    fold_size = total_span / n_splits
    results: list[PurgedFoldResult] = []

    for i in range(n_splits):
        test_start = global_start + fold_size * i
        test_end = test_start + fold_size

        train_indices: list[int] = []
        test_indices: list[int] = []
        purged = 0

        for ts, idx in timestamps:
            if test_start <= ts < test_end:
                test_indices.append(idx)
            elif ts < test_start:
                # Candidate for training
                if purge:
                    # Purge if this observation overlaps with test via embargo/horizon
                    _, embargoed_end = embargo_range(test_start, test_end, embargo_delta)
                    if ts >= test_start - embargo_delta:
                        purged += 1
                        continue
                train_indices.append(idx)

        results.append(PurgedFoldResult(
            fold_index=i,
            train_indices=train_indices,
            test_indices=test_indices,
            purged_count=purged,
            embargo_days=embargo_days,
        ))

    return results


def purged_kfold_windows(
    rows: Sequence[Mapping[str, object]],
    config: Mapping[str, object],
) -> list[WindowSpec]:
    """Convert purged K-fold results into WindowSpec objects."""
    n_splits = int(config.get("n_splits") or 5)
    embargo_days = int(config.get("embargo_days") or 5)
    horizon_days = int(config.get("horizon_days") or 5)
    purge = bool(config.get("purge_overlap", True))
    min_samples = int(config.get("min_samples_per_window") or 1000)

    folds = purged_kfold_split(rows, n_splits, embargo_days, horizon_days, purge)
    timestamps = sorted(
        (_parse_ts(row.get("ts")), idx)
        for idx, row in enumerate(rows)
        if _parse_ts(row.get("ts")) is not None
    )
    ts_list = [ts for ts, _ in timestamps]
    if not ts_list:
        return []

    global_start = ts_list[0]
    global_end = ts_list[-1]
    symbols = tuple(sorted({str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")}))
    embargo_delta = timedelta(days=embargo_days)
    horizon_delta = timedelta(days=horizon_days)
    total_span = global_end - global_start - horizon_delta
    fold_size = total_span / n_splits if total_span.days > 0 else timedelta(days=1)

    windows: list[WindowSpec] = []
    for fold in folds:
        i = fold.fold_index
        test_start = global_start + fold_size * i
        test_end = test_start + fold_size
        train_end = test_start - embargo_delta
        train_start = global_start

        if purge and train_end >= test_start:
            train_end = purge_overlap(train_start, train_end, test_start, test_end)

        val_size = max(fold_size * 0.2, timedelta(days=1))
        val_end = max(train_end - embargo_delta, train_start)
        val_start = max(val_end - val_size, train_start)

        if _count_samples(ts_list, train_start, test_end) >= min_samples:
            windows.append(WindowSpec(
                window_id=i,
                train_start=train_start,
                train_end=train_end,
                validation_start=val_start,
                validation_end=val_end,
                test_start=test_start,
                test_end=test_end,
                horizon=horizon_delta,
                embargo=embargo_delta,
                step=fold_size,
                mode="embargoed_cv",
                symbols=symbols,
                metadata={"purge_overlap": purge, "n_splits": n_splits, "fold_index": i},
            ))

    return windows
