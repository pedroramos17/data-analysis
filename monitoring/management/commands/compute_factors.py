"""Canonical command for computing Sourceflow factor values."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from sourceflow.intelligence.runtime import compute_seed_factor_values


class Command(BaseCommand):
    """Compute seed symbolic factor values into Parquet."""

    help = "Compute Sourceflow symbolic factors."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add time-bounded compute options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--as-of", default="")
        parser.add_argument("--history-start", default="")
        parser.add_argument("--history-end", default="")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Run factor computation.

        Example:
            `python manage.py compute_factors --as-of 2026-05-28T00:00:00Z`
        """
        as_of = _parsed_datetime(str(options.get("as_of", ""))) or timezone.now()
        history_end = _parsed_datetime(str(options.get("history_end", ""))) or as_of
        history_start = _history_start(options, history_end)
        paths = compute_seed_factor_values(
            connection,
            Path(settings.PARQUET_EXPORT_DIR),
            as_of,
            history_start,
            history_end,
        )
        self.stdout.write(f"Computed {len(paths)} symbolic factors")


def _history_start(options: dict[str, object], history_end: datetime) -> datetime:
    parsed = _parsed_datetime(str(options.get("history_start", "")))
    return parsed or history_end - timedelta(hours=72)


def _parsed_datetime(value: str) -> datetime | None:
    if not value:
        return None
    parsed = parse_datetime(value)
    return parsed if parsed is not None else datetime.fromisoformat(value)
