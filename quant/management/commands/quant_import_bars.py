"""Import OHLCV CSV bars for Quant multifractal analysis."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from quant.services.multifractal.data.parquet_store import write_bars_parquet
from quant.services.multifractal.data.validators import import_ohlcv_csv


class Command(BaseCommand):
    """Import canonical OHLCV bars into local Parquet."""

    help = "Import local OHLCV CSV bars into Quant multifractal Parquet storage."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register CSV import options."""
        parser.add_argument("--csv", required=True)
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--output-root", required=True)
        parser.add_argument("--asset-class", default="stock")
        parser.add_argument("--timeframe", default="1d")
        parser.add_argument("--source", default="csv")

    def handle(self, *args: object, **options: object) -> None:
        """Import, validate, and write bars."""
        bars = import_ohlcv_csv(
            Path(str(options["csv"])),
            str(options["symbol"]),
            str(options["asset_class"]),
            str(options["timeframe"]),
            str(options["source"]),
        )
        result = write_bars_parquet(bars, Path(str(options["output_root"])))
        self.stdout.write(f"bars_written={result.row_count} root={result.root_path}")
