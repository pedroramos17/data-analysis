"""Detect multifractal regimes from local feature values."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant.services.multifractal.cli_support import (
    json_text,
    parse_float_series,
    regime_feature_rows,
)
from quant.services.multifractal.regime.multifractal_regime import (
    detect_multifractal_regimes,
)


class Command(BaseCommand):
    """Run the local multifractal regime detector."""

    help = "Detect Quant multifractal regimes from comma-separated values."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register regime command options."""
        parser.add_argument("--series", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Detect and print regime report."""
        rows = regime_feature_rows(parse_float_series(str(options["series"])))
        report = detect_multifractal_regimes(rows)
        self.stdout.write(json_text(report.to_json_dict()))
