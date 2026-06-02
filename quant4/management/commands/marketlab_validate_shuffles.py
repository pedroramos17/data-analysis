"""Validate MarketLab shuffling strategies."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.marketlab.shuffling import GeneralizedTimeWindowShuffle
from quant4.services.marketlab.windows import MarketWindow


class Command(BaseCommand):
    """Run a local train-only shuffle validation."""

    help = "Validate MarketLab train-only shuffling behavior."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register shuffle validation options."""
        parser.add_argument("--values-json", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Validate a deterministic train-only shuffle."""
        values = self._values(options["values_json"])
        window = MarketWindow([0, 1], [2], [3], {})
        result = GeneralizedTimeWindowShuffle(seed=1).shuffle(values, window)
        validation_count = len(result.validation_values)
        self.stdout.write(
            f"train={len(result.train_values)} validation={validation_count} "
            f"test={len(result.test_values)}",
        )

    def _values(self, raw_value: object) -> list[float]:
        """Parse a JSON number list."""
        parsed = json.loads(str(raw_value))
        if isinstance(parsed, list):
            return [float(value) for value in parsed]
        raise ValueError(f"Invalid values {parsed!r}; expected JSON number list")
