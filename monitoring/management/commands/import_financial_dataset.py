"""Import local CSV/JSONL/parquet financial datasets."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.finance_ingestion.connectors.local_files import (
    read_local_financial_records,
)


class Command(BaseCommand):
    """Read local vendor, broker, or exported finance datasets."""

    help = "Import local financial datasets for market, macro, or fundamental data."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register local import options."""
        parser.add_argument("--path", required=True)
        parser.add_argument("--dataset-type", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Read records and report counts; persistence is intentionally explicit."""
        records = read_local_financial_records(str(options["path"]))
        self.stdout.write(
            f"Financial dataset {options['dataset_type']}: rows={len(records)} "
            f"dry_run={options['dry_run']}"
        )
