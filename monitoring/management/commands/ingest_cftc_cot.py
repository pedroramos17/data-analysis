"""Dry-run capable CFTC COT ingestion command."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.config.feature_flags import require_feature


class Command(BaseCommand):
    """Prepare CFTC Commitments of Traders ingestion."""

    help = "Ingest CFTC COT futures-only or futures-options reports."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register CFTC COT options."""
        parser.add_argument("--report-type", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Print the requested official CFTC report type."""
        require_feature("FIN_DATA_CFTC_COT")
        mode = "dry-run" if options.get("dry_run") else "planned"
        self.stdout.write(f"CFTC COT {mode}: report_type={options['report_type']}")
