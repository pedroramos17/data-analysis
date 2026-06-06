"""Core window splitting logic for time-series cross-validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from src.pipeline.windows.embargo import purge_overlap


@dataclass(frozen=True, slots=True)
class WindowSpec:
    """Immutable specification for one train/validation/test window."""

    window_id: int
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    horizon: timedelta
    embargo: timedelta
    step: timedelta
    mode: str
    symbols: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe dictionary."""
        return {
            "window_id": self.window_id,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "validation_start": self.validation_start.isoformat(),
            "validation_end": self.validation_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
            "horizon_days": self.horizon.days,
            "embargo_days": self.embargo.days,
            "step_days": self.step.days,
            "mode": self.mode,
            "symbols": list(self.symbols),
            "metadata": dict(self.metadata),
        }


def split_windows(
    rows: Sequence[Mapping[str, object]],
    config: Mapping[str, object],
) -> list[WindowSpec]:
    """Generate time-series window specs from sorted rows and config."""
    mode = str(config.get("mode") or "rolling")
    train_days = int(config.get("train_size_days") or 730)
    val_days = int(config.get("validation_size_days") or 90)
    test_days = int(config.get("test_size_days") or 90)
    step_days = int(config.get("step_size_days") or 30)
    embargo_days = int(config.get("embargo_days") or 5)
    horizon_days = int(config.get("horizon_days") or 5)
    purge = bool(config.get("purge_overlap", True))
    min_samples = int(config.get("min_samples_per_window") or 1000)

    timestamps = sorted(_parse_ts(row.get("ts")) for row in rows if _parse_ts(row.get("ts")) is not None)
    if not timestamps:
        return []

    global_start = timestamps[0]
    global_end = timestamps[-1]
    symbols = tuple(sorted({str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")}))

    train_delta = timedelta(days=train_days)
    val_delta = timedelta(days=val_days)
    test_delta = timedelta(days=test_days)
    step_delta = timedelta(days=step_days)
    embargo_delta = timedelta(days=embargo_days)
    horizon_delta = timedelta(days=horizon_days)

    if mode == "expanding":
        windows = _expanding_windows(
            global_start, global_end, train_delta, val_delta, test_delta,
            step_delta, embargo_delta, horizon_delta, symbols, purge, min_samples, timestamps,
        )
    elif mode == "anchored":
        windows = _anchored_windows(
            global_start, global_end, train_delta, val_delta, test_delta,
            step_delta, embargo_delta, horizon_delta, symbols, purge, min_samples, timestamps,
        )
    elif mode == "purged":
        windows = _purged_walk_forward(
            global_start, global_end, train_delta, val_delta, test_delta,
            step_delta, embargo_delta, horizon_delta, symbols, purge, min_samples, timestamps,
        )
    elif mode == "embargoed_cv":
        n_splits = int(config.get("n_splits") or 5)
        windows = _embargoed_cv_windows(
            global_start, global_end, n_splits, embargo_delta, horizon_delta,
            symbols, purge, min_samples, timestamps,
        )
    else:  # rolling (default)
        windows = _rolling_windows(
            global_start, global_end, train_delta, val_delta, test_delta,
            step_delta, embargo_delta, horizon_delta, symbols, purge, min_samples, timestamps,
        )

    return windows


def _rolling_windows(
    global_start: datetime,
    global_end: datetime,
    train_delta: timedelta,
    val_delta: timedelta,
    test_delta: timedelta,
    step_delta: timedelta,
    embargo_delta: timedelta,
    horizon_delta: timedelta,
    symbols: tuple[str, ...],
    purge: bool,
    min_samples: int,
    timestamps: list[datetime],
) -> list[WindowSpec]:
    windows: list[WindowSpec] = []
    window_id = 0
    # Earliest possible train start considering we need train + val + test + horizon within global_end
    required = train_delta + val_delta + test_delta + horizon_delta + embargo_delta
    if global_start + required > global_end:
        return windows

    train_start = global_start
    while True:
        train_end = train_start + train_delta
        val_start = train_end + embargo_delta
        val_end = val_start + val_delta
        test_start = val_end + embargo_delta
        test_end = test_start + test_delta

        if test_end + horizon_delta > global_end:
            break

        train_start_actual, train_end_actual = train_start, train_end
        if purge:
            train_end_actual = purge_overlap(train_start, train_end, val_start, val_end)

        if _count_samples(timestamps, train_start_actual, test_end) >= min_samples:
            windows.append(WindowSpec(
                window_id=window_id,
                train_start=train_start_actual,
                train_end=train_end_actual,
                validation_start=val_start,
                validation_end=val_end,
                test_start=test_start,
                test_end=test_end,
                horizon=horizon_delta,
                embargo=embargo_delta,
                step=step_delta,
                mode="rolling",
                symbols=symbols,
                metadata={"purge_overlap": purge},
            ))
            window_id += 1

        train_start += step_delta
        # Prevent infinite loops when step is 0 or negative
        if step_delta.days <= 0:
            break
        if train_start > global_end - required:
            break

    return windows


def _expanding_windows(
    global_start: datetime,
    global_end: datetime,
    train_delta: timedelta,
    val_delta: timedelta,
    test_delta: timedelta,
    step_delta: timedelta,
    embargo_delta: timedelta,
    horizon_delta: timedelta,
    symbols: tuple[str, ...],
    purge: bool,
    min_samples: int,
    timestamps: list[datetime],
) -> list[WindowSpec]:
    windows: list[WindowSpec] = []
    window_id = 0
    required = train_delta + val_delta + test_delta + horizon_delta + embargo_delta
    if global_start + required > global_end:
        return windows

    # Expanding: train always starts at global_start and grows
    train_start = global_start
    current_train_end = train_start + train_delta

    while True:
        val_start = current_train_end + embargo_delta
        val_end = val_start + val_delta
        test_start = val_end + embargo_delta
        test_end = test_start + test_delta

        if test_end + horizon_delta > global_end:
            break

        train_end_actual = current_train_end
        if purge:
            train_end_actual = purge_overlap(train_start, current_train_end, val_start, val_end)

        if _count_samples(timestamps, train_start, test_end) >= min_samples:
            windows.append(WindowSpec(
                window_id=window_id,
                train_start=train_start,
                train_end=train_end_actual,
                validation_start=val_start,
                validation_end=val_end,
                test_start=test_start,
                test_end=test_end,
                horizon=horizon_delta,
                embargo=embargo_delta,
                step=step_delta,
                mode="expanding",
                symbols=symbols,
                metadata={"purge_overlap": purge},
            ))
            window_id += 1

        current_train_end += step_delta
        if step_delta.days <= 0:
            break
        if current_train_end > global_end - val_delta - test_delta - embargo_delta - horizon_delta:
            break

    return windows


def _anchored_windows(
    global_start: datetime,
    global_end: datetime,
    train_delta: timedelta,
    val_delta: timedelta,
    test_delta: timedelta,
    step_delta: timedelta,
    embargo_delta: timedelta,
    horizon_delta: timedelta,
    symbols: tuple[str, ...],
    purge: bool,
    min_samples: int,
    timestamps: list[datetime],
) -> list[WindowSpec]:
    """Anchored walk-forward: train anchored at start, test slides forward."""
    windows: list[WindowSpec] = []
    window_id = 0
    required = train_delta + val_delta + test_delta + horizon_delta + embargo_delta
    if global_start + required > global_end:
        return windows

    # Similar to expanding but we can optionally keep train fixed at initial size
    # and slide only test, or let train grow. Here: train grows from anchor.
    train_start = global_start
    current_train_end = train_start + train_delta

    while True:
        val_start = current_train_end + embargo_delta
        val_end = val_start + val_delta
        test_start = val_end + embargo_delta
        test_end = test_start + test_delta

        if test_end + horizon_delta > global_end:
            break

        train_end_actual = current_train_end
        if purge:
            train_end_actual = purge_overlap(train_start, current_train_end, val_start, val_end)

        if _count_samples(timestamps, train_start, test_end) >= min_samples:
            windows.append(WindowSpec(
                window_id=window_id,
                train_start=train_start,
                train_end=train_end_actual,
                validation_start=val_start,
                validation_end=val_end,
                test_start=test_start,
                test_end=test_end,
                horizon=horizon_delta,
                embargo=embargo_delta,
                step=step_delta,
                mode="anchored",
                symbols=symbols,
                metadata={"purge_overlap": purge, "anchored_at": global_start.isoformat()},
            ))
            window_id += 1

        current_train_end += step_delta
        if step_delta.days <= 0:
            break
        if current_train_end > global_end - val_delta - test_delta - embargo_delta - horizon_delta:
            break

    return windows


def _purged_walk_forward(
    global_start: datetime,
    global_end: datetime,
    train_delta: timedelta,
    val_delta: timedelta,
    test_delta: timedelta,
    step_delta: timedelta,
    embargo_delta: timedelta,
    horizon_delta: timedelta,
    symbols: tuple[str, ...],
    purge: bool,
    min_samples: int,
    timestamps: list[datetime],
) -> list[WindowSpec]:
    """Purged walk-forward is rolling with mandatory purge."""
    windows = _rolling_windows(
        global_start, global_end, train_delta, val_delta, test_delta,
        step_delta, embargo_delta, horizon_delta, symbols, True, min_samples, timestamps,
    )
    # Re-tag mode
    return [WindowSpec(
        window_id=w.window_id,
        train_start=w.train_start,
        train_end=w.train_end,
        validation_start=w.validation_start,
        validation_end=w.validation_end,
        test_start=w.test_start,
        test_end=w.test_end,
        horizon=w.horizon,
        embargo=w.embargo,
        step=w.step,
        mode="purged",
        symbols=w.symbols,
        metadata={**w.metadata, "purge_overlap": True},
    ) for w in windows]


def _embargoed_cv_windows(
    global_start: datetime,
    global_end: datetime,
    n_splits: int,
    embargo_delta: timedelta,
    horizon_delta: timedelta,
    symbols: tuple[str, ...],
    purge: bool,
    min_samples: int,
    timestamps: list[datetime],
) -> list[WindowSpec]:
    """K-fold cross-validation with embargo between folds."""
    windows: list[WindowSpec] = []
    if n_splits < 2:
        return windows

    total_span = global_end - global_start - horizon_delta
    if total_span.days <= 0:
        return windows

    fold_size = total_span / n_splits
    for i in range(n_splits):
        test_start = global_start + fold_size * i
        test_end = test_start + fold_size

        # Train is everything before test_start minus embargo
        train_end = test_start - embargo_delta
        if train_end <= global_start:
            continue

        train_start = global_start
        train_end_actual = train_end
        if purge:
            train_end_actual = purge_overlap(train_start, train_end, test_start, test_end)

        # Validation is a slice before test within the train region
        val_size = max(fold_size * 0.2, timedelta(days=1))
        val_end = train_end_actual - embargo_delta
        val_start = max(val_end - val_size, train_start)

        if _count_samples(timestamps, train_start, test_end) >= min_samples:
            windows.append(WindowSpec(
                window_id=i,
                train_start=train_start,
                train_end=train_end_actual,
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


def _parse_ts(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _count_samples(timestamps: list[datetime], start: datetime, end: datetime) -> int:
    return sum(1 for ts in timestamps if start <= ts <= end)
