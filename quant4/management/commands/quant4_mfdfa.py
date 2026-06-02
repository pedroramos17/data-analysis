"""Run MF-DFA from a local numeric series."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.multifractal.cli_support import json_text, parse_float_series
from quant4.services.multifractal.core.mfdfa import run_mfdfa


class Command(BaseCommand):
    """Run MF-DFA and print a compact JSON summary."""

    help = "Run Quant4 MF-DFA over a comma-separated numeric series."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register MF-DFA options."""
        parser.add_argument("--series", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Execute MF-DFA locally."""
        result = run_mfdfa(parse_float_series(str(options["series"])))
        payload = result.summary | {
            "method": "mfdfa",
            "valid_scale_count": result.valid_scale_count,
        }
        self.stdout.write(json_text(payload))
