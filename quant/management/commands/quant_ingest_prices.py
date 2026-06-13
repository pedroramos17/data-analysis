"""Register Quant price dataset metadata."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from quant.models import Asset
from quant.services.data_ingestion import save_market_dataset_metadata


class Command(BaseCommand):
    """Store metadata for a local price dataset."""

    help = "Register Quant market dataset metadata for local price data."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register price metadata options."""
        parser.add_argument("--name", required=True)
        parser.add_argument("--source", required=True)
        parser.add_argument("--frequency", required=True)
        parser.add_argument("--symbol", default="")
        parser.add_argument("--metadata-json", default="{}")

    def handle(self, *args: object, **options: object) -> None:
        """Persist dataset metadata and print the dataset id."""
        dataset = save_market_dataset_metadata(
            name=str(options["name"]),
            source=str(options["source"]),
            frequency=str(options["frequency"]),
            asset=self._asset(str(options["symbol"])),
            metadata=self._metadata(str(options["metadata_json"])),
            provenance={"command": "quant_ingest_prices"},
        )
        self.stdout.write(f"market_dataset_id={dataset.pk}")

    def _metadata(self, raw_value: str) -> dict[str, object]:
        """Parse a JSON object metadata option."""
        try:
            metadata = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid metadata JSON {raw_value!r}; expected JSON object"
            ) from exc
        if isinstance(metadata, dict):
            return metadata
        raise ValueError(f"Invalid metadata {metadata!r}; expected JSON object")

    def _asset(self, symbol: str) -> Asset | None:
        """Return the registered asset for an optional symbol."""
        if not symbol:
            return None
        return Asset.objects.filter(symbol=symbol.upper()).first()
