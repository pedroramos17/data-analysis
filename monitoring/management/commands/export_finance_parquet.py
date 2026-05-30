"""Export finance rows to parquet."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.finance_ingestion.parquet_export import write_finance_parquet


class Command(BaseCommand):
    """Export finance rows using the project pyarrow wrapper."""

    help = "Export finance dataset rows to parquet."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register export options."""
        parser.add_argument("--path", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Write an empty parquet table unless dry-run is selected."""
        if not options["dry_run"]:
            write_finance_parquet([], str(options["path"]))
        self.stdout.write(
            f"Finance parquet path={options['path']} dry_run={options['dry_run']}"
        )
