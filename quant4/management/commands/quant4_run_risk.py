"""Run Quant4 local risk analysis."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.risk.reports import run_risk_analysis
from quant4.services.run_metadata import parse_iso_date_range


class Command(BaseCommand):
    """Persist a Quant4 risk run."""

    help = "Run Quant4 local risk models on JSON returns, prices, and volumes."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register risk run options."""
        parser.add_argument("--name", default="quant4-risk-run")
        parser.add_argument("--returns-json", required=True)
        parser.add_argument("--prices-json", required=True)
        parser.add_argument("--volumes-json", required=True)
        parser.add_argument("--data-start", required=True)
        parser.add_argument("--data-end", required=True)
        parser.add_argument("--split-start", required=True)
        parser.add_argument("--split-end", required=True)
        parser.add_argument("--random-seed", type=int, default=0)

    def handle(self, *args: object, **options: object) -> None:
        """Create a risk run and print its id."""
        run = run_risk_analysis(
            name=str(options["name"]),
            returns=self._float_list(options["returns_json"], "returns-json"),
            prices=self._float_list(options["prices_json"], "prices-json"),
            volumes=self._float_list(options["volumes_json"], "volumes-json"),
            data_range=parse_iso_date_range(
                options["data_start"],
                options["data_end"],
                "data_range",
            ),
            split_range=parse_iso_date_range(
                options["split_start"],
                options["split_end"],
                "split_range",
            ),
            random_seed=int(options["random_seed"]),
            provenance={"command": "quant4_run_risk"},
        )
        self.stdout.write(f"risk_run_id={run.pk}")

    def _float_list(self, raw_value: object, label: str) -> list[float]:
        """Parse a JSON list of numbers."""
        parsed = json.loads(str(raw_value))
        if isinstance(parsed, list):
            return [float(value) for value in parsed]
        raise ValueError(f"Invalid {label} {parsed!r}; expected JSON number list")
