"""Prepare MarketLab windows through shared Quant4 artifacts."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.marketlab.windows import (
    PurgedWalkForwardWindowBuilder,
    persist_window_artifact,
)


class Command(BaseCommand):
    """Create a MarketLab window artifact."""

    help = "Prepare MarketLab purged walk-forward windows."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register MarketLab window options."""
        parser.add_argument("--name", default="marketlab-window")
        parser.add_argument("--values-json", required=True)
        parser.add_argument("--train-size", type=int, default=20)
        parser.add_argument("--test-size", type=int, default=5)
        parser.add_argument("--embargo", type=int, default=1)
        parser.add_argument("--horizon", type=int, default=1)

    def handle(self, *args: object, **options: object) -> None:
        """Persist the first prepared MarketLab window."""
        values = self._values(options["values_json"])
        builder = PurgedWalkForwardWindowBuilder(
            int(options["train_size"]),
            int(options["test_size"]),
            int(options["embargo"]),
        )
        windows = builder.build(values, horizon=int(options["horizon"]))
        if not windows:
            raise ValueError(
                f"Invalid values length {len(values)}; expected enough rows"
            )
        artifact = persist_window_artifact(str(options["name"]), windows[0])
        self.stdout.write(f"window_artifact_id={artifact.pk}")

    def _values(self, raw_value: object) -> list[float]:
        """Parse a JSON number list."""
        parsed = json.loads(str(raw_value))
        if isinstance(parsed, list):
            return [float(value) for value in parsed]
        raise ValueError(f"Invalid values {parsed!r}; expected JSON number list")
