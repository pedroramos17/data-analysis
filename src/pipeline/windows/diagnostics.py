"""Window diagnostics: leakage checks, gap analysis, and reproducibility audits."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.pipeline.windows.embargo import check_embargo_violation
from src.pipeline.windows.splitter import WindowSpec, _parse_ts


@dataclass(frozen=True, slots=True)
class WindowDiagnostics:
    """Diagnostic report for a single window."""

    window_id: int
    train_rows: int
    validation_rows: int
    test_rows: int
    train_test_gap_days: float
    train_val_gap_days: float
    val_test_gap_days: float
    embargo_violations: int
    future_leakage_violations: int
    horizon_compliant: bool
    min_samples_met: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "window_id": self.window_id,
            "train_rows": self.train_rows,
            "validation_rows": self.validation_rows,
            "test_rows": self.test_rows,
            "train_test_gap_days": round(self.train_test_gap_days, 6),
            "train_val_gap_days": round(self.train_val_gap_days, 6),
            "val_test_gap_days": round(self.val_test_gap_days, 6),
            "embargo_violations": self.embargo_violations,
            "future_leakage_violations": self.future_leakage_violations,
            "horizon_compliant": self.horizon_compliant,
            "min_samples_met": self.min_samples_met,
            "metadata": dict(self.metadata),
        }


def diagnose_window(
    window: WindowSpec,
    rows: Sequence[Mapping[str, object]],
    min_samples: int = 1000,
) -> WindowDiagnostics:
    """Run full diagnostic suite on one window."""
    train_rows = _filter_rows(rows, window.train_start, window.train_end)
    val_rows = _filter_rows(rows, window.validation_start, window.validation_end)
    test_rows = _filter_rows(rows, window.test_start, window.test_end)

    train_latest = _latest_ts(train_rows)
    val_earliest = _earliest_ts(val_rows)
    val_latest = _latest_ts(val_rows)
    test_earliest = _earliest_ts(test_rows)

    embargo_violations = 0
    if train_latest and val_earliest and check_embargo_violation(train_latest, val_earliest, window.embargo):
        embargo_violations += 1
    if val_latest and test_earliest and check_embargo_violation(val_latest, test_earliest, window.embargo):
        embargo_violations += 1

    future_leakage = _count_future_leakage(train_rows, window.test_start)
    horizon_compliant = _check_horizon_compliance(window, rows)

    return WindowDiagnostics(
        window_id=window.window_id,
        train_rows=len(train_rows),
        validation_rows=len(val_rows),
        test_rows=len(test_rows),
        train_test_gap_days=_gap_days(train_latest, test_earliest),
        train_val_gap_days=_gap_days(train_latest, val_earliest),
        val_test_gap_days=_gap_days(val_latest, test_earliest),
        embargo_violations=embargo_violations,
        future_leakage_violations=future_leakage,
        horizon_compliant=horizon_compliant,
        min_samples_met=(len(train_rows) + len(val_rows) + len(test_rows)) >= min_samples,
        metadata={"symbols": list(window.symbols)},
    )


def diagnose_all_windows(
    windows: Sequence[WindowSpec],
    rows: Sequence[Mapping[str, object]],
    min_samples: int = 1000,
) -> list[WindowDiagnostics]:
    """Run diagnostics on all windows and return sorted list."""
    return [diagnose_window(w, rows, min_samples) for w in windows]


def _filter_rows(
    rows: Sequence[Mapping[str, object]],
    start: datetime,
    end: datetime,
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in rows:
        ts = _parse_ts(row.get("ts"))
        if ts is not None and start <= ts <= end:
            result.append(dict(row))
    return result


def _latest_ts(rows: Sequence[Mapping[str, object]]) -> datetime | None:
    timestamps = [_parse_ts(row.get("ts")) for row in rows]
    valid = [ts for ts in timestamps if ts is not None]
    return max(valid) if valid else None


def _earliest_ts(rows: Sequence[Mapping[str, object]]) -> datetime | None:
    timestamps = [_parse_ts(row.get("ts")) for row in rows]
    valid = [ts for ts in timestamps if ts is not None]
    return min(valid) if valid else None


def _gap_days(latest: datetime | None, earliest: datetime | None) -> float:
    if latest is None or earliest is None:
        return float("inf")
    delta = earliest - latest
    return delta.total_seconds() / 86400.0


def _count_future_leakage(
    train_rows: Sequence[Mapping[str, object]],
    test_start: datetime,
) -> int:
    """Count train rows with timestamps at or after test_start."""
    count = 0
    for row in train_rows:
        ts = _parse_ts(row.get("ts"))
        if ts is not None and ts >= test_start:
            count += 1
    return count


def _check_horizon_compliance(
    window: WindowSpec,
    rows: Sequence[Mapping[str, object]],
) -> bool:
    """Check that no train row's horizon extends into test period.

    A row at time t with horizon h is compliant if t + h <= test_start.
    """
    for row in rows:
        ts = _parse_ts(row.get("ts"))
        if ts is None:
            continue
        if window.train_start <= ts <= window.train_end:
            if ts + window.horizon > window.test_start:
                return False
    return True
