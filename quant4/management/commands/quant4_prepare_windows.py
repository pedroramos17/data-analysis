"""Create Quant4 window artifact metadata."""

from __future__ import annotations

import json
from datetime import date

from django.core.management.base import BaseCommand, CommandParser

from quant4.models import MarketDataset
from quant4.services.windows import create_window_artifact


class Command(BaseCommand):
    """Prepare metadata for a leakage-safe window artifact."""

    help = "Create Quant4 window artifact metadata."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register window preparation options."""
        parser.add_argument("--dataset-id", type=int, required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--split-json", default="{}")
        parser.add_argument("--config-json", default="{}")
        parser.add_argument("--random-seed", type=int, default=0)
        parser.add_argument("--data-start", default="")
        parser.add_argument("--data-end", default="")
        parser.add_argument("--split-start", default="")
        parser.add_argument("--split-end", default="")

    def handle(self, *args: object, **options: object) -> None:
        """Persist a window artifact and print its id."""
        dataset = MarketDataset.objects.get(pk=options["dataset_id"])
        artifact = create_window_artifact(
            dataset=dataset,
            name=str(options["name"]),
            split_metadata=self._json_object(options["split_json"]),
            config=self._json_object(options["config_json"]),
            random_seed=int(options["random_seed"]),
            data_range=self._date_range(options, "data"),
            split_range=self._date_range(options, "split"),
            provenance={"command": "quant4_prepare_windows"},
        )
        self.stdout.write(f"window_artifact_id={artifact.pk}")

    def _json_object(self, raw_value: object) -> dict[str, object]:
        """Parse a JSON object option."""
        text = str(raw_value)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON value {text!r}; expected object") from exc
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"Invalid JSON value {parsed!r}; expected object")

    def _date_range(
        self,
        options: dict[str, object],
        prefix: str,
    ) -> tuple[date | None, date | None]:
        """Parse start/end date options for one range prefix."""
        return (
            self._optional_date(str(options[f"{prefix}_start"])),
            self._optional_date(str(options[f"{prefix}_end"])),
        )

    def _optional_date(self, raw_value: str) -> date | None:
        """Parse an optional ISO date."""
        if not raw_value:
            return None
        try:
            return date.fromisoformat(raw_value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid date {raw_value!r}; expected YYYY-MM-DD"
            ) from exc
