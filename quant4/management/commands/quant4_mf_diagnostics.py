"""Run multifractal diagnostics from a local numeric series."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.multifractal.cli_support import json_text, parse_float_series
from quant4.services.multifractal.core.diagnostics import run_multifractal_diagnostics


class Command(BaseCommand):
    """Run shuffle, surrogate, and bootstrap diagnostics."""

    help = "Run local Quant4 multifractal diagnostics over a numeric series."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register diagnostic options."""
        parser.add_argument("--series", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Execute diagnostics with small deterministic defaults."""
        report = run_multifractal_diagnostics(
            parse_float_series(str(options["series"])),
            seed=17,
            bootstrap_count=4,
            finite_size_simulations=2,
        )
        self.stdout.write(json_text(report.to_json_dict()))
