"""Run a MarketLab benchmark through shared Quant4 ModelRun."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.marketlab.evaluation import run_marketlab_benchmark


class Command(BaseCommand):
    """Persist a MarketLab benchmark result."""

    help = "Run MarketLab benchmark metrics and persist a shared ModelRun."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register benchmark options."""
        parser.add_argument("--name", default="marketlab-benchmark")
        parser.add_argument("--predictions-json", required=True)
        parser.add_argument("--labels-json", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Create a shared ModelRun benchmark."""
        run = run_marketlab_benchmark(
            str(options["name"]),
            self._values(options["predictions_json"], "predictions"),
            self._values(options["labels_json"], "labels"),
        )
        self.stdout.write(f"model_run_id={run.pk}")

    def _values(self, raw_value: object, label: str) -> list[float]:
        """Parse a JSON number list."""
        parsed = json.loads(str(raw_value))
        if isinstance(parsed, list):
            return [float(value) for value in parsed]
        raise ValueError(f"Invalid {label} {parsed!r}; expected JSON number list")
