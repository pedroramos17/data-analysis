"""Compute return Parquet datasets from Quant4 multifractal bars."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.multifractal.data.parquet_store import (
    read_bars_parquet,
    write_returns_parquet,
)
from quant4.services.multifractal.data.validators import generate_return_records


class Command(BaseCommand):
    """Compute adjacent returns from local bar datasets."""

    help = "Compute Quant4 multifractal return records from local Parquet bars."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register return-generation options."""
        parser.add_argument("--bars-root", required=True)
        parser.add_argument("--output-root", required=True)
        parser.add_argument("--symbol", default=None)
        parser.add_argument("--timeframe", default=None)
        parser.add_argument("--price-col", default="close")
        parser.add_argument("--source-dataset-id", default="cli")

    def handle(self, *args: object, **options: object) -> None:
        """Read bars, generate returns, and write Parquet."""
        bars = read_bars_parquet(
            str(options["bars_root"]),
            symbol=options["symbol"],
            timeframe=options["timeframe"],
        )
        records = generate_return_records(
            bars,
            price_col=str(options["price_col"]),
            source_dataset_id=str(options["source_dataset_id"]),
        )
        result = write_returns_parquet(records, Path(str(options["output_root"])))
        self.stdout.write(f"returns_written={result.row_count} root={result.root_path}")
