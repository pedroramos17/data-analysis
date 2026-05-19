"""Synchronize bundled JSON catalogs into operational tables."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.catalog_sync import sync_catalogs


class Command(BaseCommand):
    """Synchronize selected source catalogs.

    Example:
        `python manage.py sync_catalogs --feeds --dry-run`
    """

    help = "Synchronize bundled JSON catalogs into SQLite rows."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register catalog sync options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--feeds", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Run catalog synchronization and print a compact summary.

        Example:
            Django calls this after parsing command options.
        """
        feeds = bool(options["feeds"]) or not _any_catalog_flag(options)
        results = sync_catalogs(feeds=feeds, dry_run=bool(options["dry_run"]))
        for result in results:
            self.stdout.write(_result_line(result))


def _any_catalog_flag(options: dict[str, object]) -> bool:
    return bool(options["feeds"])


def _result_line(result: object) -> str:
    mode = "dry-run" if result.dry_run else "synced"
    changed = "changed" if result.changed else "unchanged"
    return f"{result.catalog_name}: {mode} {result.source_count} rows ({changed})"
