"""Feature-flagged yfinance-like research ingestion command."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.finance_ingestion.connectors.yahoo_research import ingest_yahoo_research


class Command(BaseCommand):
    """Prepare yfinance-like research ingestion."""

    help = "Ingest yfinance-like public research data when enabled."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register symbol options."""
        parser.add_argument("--symbol", action="append", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Build the flagged yfinance-like ingestion plan."""
        rows = ingest_yahoo_research([str(item) for item in options["symbol"]])
        self.stdout.write(
            f"Yahoo research rows={len(rows)} dry_run={options['dry_run']}"
        )
