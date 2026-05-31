"""Compute one multifractal feature row from a local series."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.multifractal.cli_support import json_text, parse_float_series
from quant4.services.multifractal.core.types import MFDFAConfig
from quant4.services.multifractal.features.multifractal_features import (
    compute_multifractal_feature_row,
)


class Command(BaseCommand):
    """Compute core multifractal features for one symbol/window."""

    help = "Compute Quant4 multifractal feature row from a numeric series."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register feature-generation options."""
        parser.add_argument("--series", required=True)
        parser.add_argument("--symbol", default="LOCAL")
        parser.add_argument("--window-id", default="cli")

    def handle(self, *args: object, **options: object) -> None:
        """Compute and print one feature row."""
        row = compute_multifractal_feature_row(
            str(options["symbol"]),
            parse_float_series(str(options["series"])),
            MFDFAConfig(),
            str(options["window_id"]),
        )
        self.stdout.write(json_text(row))
