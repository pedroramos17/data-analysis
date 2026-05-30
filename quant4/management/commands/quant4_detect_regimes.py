"""Run Quant4 local regime detection."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.regimes.reports import create_regime_run


class Command(BaseCommand):
    """Persist a Quant4 regime detection run."""

    help = "Run Quant4 local regime detectors on JSON returns and prices."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register regime detection options."""
        parser.add_argument("--name", default="quant4-regime-run")
        parser.add_argument("--returns-json", required=True)
        parser.add_argument("--prices-json", required=True)
        parser.add_argument("--random-seed", type=int, default=0)

    def handle(self, *args: object, **options: object) -> None:
        """Create a regime run and print its id."""
        run = create_regime_run(
            name=str(options["name"]),
            returns=self._float_list(options["returns_json"], "returns-json"),
            prices=self._float_list(options["prices_json"], "prices-json"),
            random_seed=int(options["random_seed"]),
            provenance={"command": "quant4_detect_regimes"},
        )
        self.stdout.write(f"regime_run_id={run.pk}")

    def _float_list(self, raw_value: object, label: str) -> list[float]:
        """Parse a JSON list of numbers."""
        parsed = json.loads(str(raw_value))
        if isinstance(parsed, list):
            return [float(value) for value in parsed]
        raise ValueError(f"Invalid {label} {parsed!r}; expected JSON number list")
