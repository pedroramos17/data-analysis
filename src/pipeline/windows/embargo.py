"""Embargo and purge logic to prevent information leakage."""

from __future__ import annotations

from datetime import datetime, timedelta


def embargo_range(start: datetime, end: datetime, embargo: timedelta) -> tuple[datetime, datetime]:
    """Return the embargoed range: original range plus embargo after end.

    Any observation whose timestamp falls within the embargoed range is
    considered contaminated and must be excluded from an earlier split.
    """
    return start, end + embargo


def purge_overlap(
    train_start: datetime,
    train_end: datetime,
    test_start: datetime,
    test_end: datetime,
) -> datetime:
    """Return the new train_end after purging overlap with the test period.

    The purge removes any training observation whose information could leak
    into the test set. This is conservative: train_end is moved to before
    test_start, and any overlap is eliminated.
    """
    if train_end >= test_start:
        # Overlap exists; truncate train to just before test starts.
        # Use a microsecond buffer to make the boundary strict.
        return test_start - timedelta(microseconds=1)
    return train_end


def check_embargo_violation(
    train_latest: datetime,
    test_earliest: datetime,
    embargo: timedelta,
) -> bool:
    """Return True if the gap between train and test violates the embargo."""
    gap = test_earliest - train_latest
    return gap < embargo


def apply_embargo(
    timestamps: list[datetime],
    cutoff: datetime,
    embargo: timedelta,
) -> list[datetime]:
    """Filter timestamps, keeping only those before cutoff - embargo."""
    boundary = cutoff - embargo
    return [ts for ts in timestamps if ts <= boundary]
