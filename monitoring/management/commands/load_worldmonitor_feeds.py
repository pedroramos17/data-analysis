"""Load the curated WorldMonitor-style RSS feed catalog."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from monitoring.catalog_sync import sync_worldmonitor_feeds


class Command(BaseCommand):
    """Load validated RSS catalog rows into the source registry.

    Example:
        `python manage.py load_worldmonitor_feeds`
    """

    help = "Load monitoring/catalogs/worldmonitor_feeds.json into Source rows."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add optional catalog and allowlist paths.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--catalog")
        parser.add_argument("--allowed-domains")

    def handle(self, *args: object, **options: object) -> None:
        """Validate and upsert the feed catalog.

        Example:
            Django calls this after parsing command options.
        """
        catalog_path = _optional_path(options.get("catalog"))
        domains_path = _optional_path(options.get("allowed_domains"))
        result = sync_worldmonitor_feeds(
            dry_run=False,
            catalog_path=catalog_path or _default_catalog_path(),
            allowed_domains_path=domains_path or _default_domains_path(),
        )
        self.stdout.write(
            f"Loaded {result.source_count} WorldMonitor-style RSS sources"
        )


def _optional_path(value: object) -> Path | None:
    if value is None:
        return None
    return Path(str(value))


def _default_catalog_path() -> Path:
    from monitoring.catalog import DEFAULT_FEED_CATALOG

    return DEFAULT_FEED_CATALOG


def _default_domains_path() -> Path:
    from monitoring.catalog import DEFAULT_ALLOWED_DOMAINS

    return DEFAULT_ALLOWED_DOMAINS
