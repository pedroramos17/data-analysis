"""Compute multifractal risk from a local return series."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.multifractal.cli_support import json_text, parse_float_series
from quant4.services.multifractal.defaults import (
    REPORT_RISK_DELTA_ALPHA,
    REPORT_RISK_INTERMITTENCY,
)
from quant4.services.multifractal.risk.multifractal_risk import (
    compute_asset_multifractal_risk,
)


class Command(BaseCommand):
    """Compute separated risk diagnostics."""

    help = "Compute Quant4 multifractal risk from a comma-separated return series."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register risk command options."""
        parser.add_argument("--series", required=True)
        parser.add_argument(
            "--delta-alpha",
            type=float,
            default=REPORT_RISK_DELTA_ALPHA,
        )
        parser.add_argument(
            "--intermittency",
            type=float,
            default=REPORT_RISK_INTERMITTENCY,
        )

    def handle(self, *args: object, **options: object) -> None:
        """Compute and print risk payload."""
        risk = compute_asset_multifractal_risk(
            parse_float_series(str(options["series"])),
            {
                "delta_alpha": float(options["delta_alpha"]),
                "intermittency_proxy": float(options["intermittency"]),
            },
        )
        self.stdout.write(json_text(risk.to_json_dict()))
