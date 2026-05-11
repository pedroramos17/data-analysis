"""Load the curated WorldMonitor-style RSS feed catalog."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from monitoring.catalog import load_feed_catalog, upsert_catalog_sources


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
        rows = load_feed_catalog(*_catalog_args(catalog_path, domains_path))
        count = upsert_catalog_sources(rows)
        self.stdout.write(f"Loaded {count} WorldMonitor-style RSS sources")


def _optional_path(value: object) -> Path | None:
    if value is None:
        return None
    return Path(str(value))


def _catalog_args(
    catalog_path: Path | None,
    domains_path: Path | None,
) -> tuple[Path, ...]:
    if catalog_path is not None and domains_path is not None:
        return (catalog_path, domains_path)
    if catalog_path is not None:
        return (catalog_path,)
    return ()
