"""Dry-run capable FRED series ingestion command."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.config.feature_flags import require_feature


class Command(BaseCommand):
    """Prepare FRED macro series ingestion."""

    help = "Ingest FRED macro series observations and metadata."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register FRED options."""
        parser.add_argument("--series", action="append", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Print the requested official FRED series list."""
        require_feature("FIN_DATA_FRED")
        series = ",".join(options["series"])
        mode = "dry-run" if options.get("dry_run") else "planned"
        self.stdout.write(f"FRED {mode}: series={series}")
