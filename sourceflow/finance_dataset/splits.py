"""Walk-forward and embargoed split helpers."""

from __future__ import annotations


def walk_forward_splits(
    row_count: int, train_size: int, test_size: int
) -> list[tuple[slice, slice]]:
    """Return sequential walk-forward train/test slices.

    Example:
        `splits = walk_forward_splits(100, 60, 10)`
    """
    splits: list[tuple[slice, slice]] = []
    start = 0
    while start + train_size + test_size <= row_count:
        train = slice(start, start + train_size)
        test = slice(start + train_size, start + train_size + test_size)
        splits.append((train, test))
        start += test_size
    return splits


def purged_embargo_split(
    row_count: int,
    train_end: int,
    test_size: int,
    embargo: int,
) -> tuple[slice, slice]:
    """Return train/test slices separated by an embargo gap.

    Example:
        `train, test = purged_embargo_split(100, 60, 10, 5)`
    """
    train = slice(0, max(0, train_end - embargo))
    test_start = min(row_count, train_end + embargo)
    return train, slice(test_start, min(row_count, test_start + test_size))
