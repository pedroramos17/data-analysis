"""Dry-run capable SEC EDGAR ingestion command."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.finance_ingestion.connectors.sec_edgar import submission_urls


class Command(BaseCommand):
    """Prepare SEC EDGAR official API ingestion."""

    help = "Ingest SEC EDGAR submissions and XBRL facts."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register SEC EDGAR options."""
        parser.add_argument("--cik", required=True)
        parser.add_argument("--forms", default="10-K,10-Q")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Print the official endpoints used for ingestion."""
        urls = submission_urls(str(options["cik"]))
        forms = str(options["forms"])
        mode = "dry-run" if options.get("dry_run") else "planned"
        self.stdout.write(f"SEC EDGAR {mode}: forms={forms} urls={urls}")
