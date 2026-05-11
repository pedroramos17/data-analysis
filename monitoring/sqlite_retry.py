"""Retry helpers for short SQLite write-lock bursts."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from django.db import OperationalError, close_old_connections

ResultT = TypeVar("ResultT")


def run_with_sqlite_retry(
    callback: Callable[[], ResultT], attempts: int = 4
) -> ResultT:
    """Run a write operation with short retries for SQLite locks.

    Example:
        `result = run_with_sqlite_retry(lambda: score_source_reputations())`
    """
    for attempt in range(attempts):
        try:
            return callback()
        except OperationalError as error:
            if (
                "database is locked" not in str(error).lower()
                or attempt == attempts - 1
            ):
                raise
            close_old_connections()
            time.sleep(0.25 * (attempt + 1))
    raise OperationalError("SQLite retry exhausted; expected available database")
