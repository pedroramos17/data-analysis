"""Run multifractal diagnostics from a local numeric series."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant.services.multifractal.cli_support import json_text, parse_float_series
from quant.services.multifractal.core.diagnostics import run_multifractal_diagnostics
from quant.services.multifractal.core.types import MFDFAConfig
from quant.services.multifractal.defaults import (
    DEFAULT_DIAGNOSTIC_SEED,
    DIAGNOSTIC_BOOTSTRAP_COUNT,
    DIAGNOSTIC_FINITE_SIZE_SIMULATIONS,
)


class Command(BaseCommand):
    """Run shuffle, surrogate, and bootstrap diagnostics."""

    help = "Run local Quant multifractal diagnostics over a numeric series."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register diagnostic options."""
        parser.add_argument("--series", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Execute diagnostics with small deterministic defaults."""
        report = run_multifractal_diagnostics(
            parse_float_series(str(options["series"])),
            MFDFAConfig(),
            seed=DEFAULT_DIAGNOSTIC_SEED,
            bootstrap_count=DIAGNOSTIC_BOOTSTRAP_COUNT,
            finite_size_simulations=DIAGNOSTIC_FINITE_SIZE_SIMULATIONS,
        )
        self.stdout.write(json_text(report.to_json_dict()))
