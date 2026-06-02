"""Run MarketLab regime detection fallback."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.marketlab.change_points import MeanShiftRegimeDetector


class Command(BaseCommand):
    """Run a lightweight MarketLab regime detector."""

    help = "Run MarketLab local mean-shift regime detection."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register detector options."""
        parser.add_argument("--values-json", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Print regime detection metadata."""
        result = MeanShiftRegimeDetector().detect(self._values(options["values_json"]))
        self.stdout.write(json.dumps(result, sort_keys=True))

    def _values(self, raw_value: object) -> list[float]:
        """Parse a JSON number list."""
        parsed = json.loads(str(raw_value))
        if isinstance(parsed, list):
            return [float(value) for value in parsed]
        raise ValueError(f"Invalid values {parsed!r}; expected JSON number list")
