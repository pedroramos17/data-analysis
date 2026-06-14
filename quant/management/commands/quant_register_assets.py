"""Register Quant assets from CLI arguments."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant.services.assets import register_assets


class Command(BaseCommand):
    """Register local research assets."""

    help = "Register Quant assets idempotently."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register asset options."""
        parser.add_argument("--symbol", action="append", required=True)
        parser.add_argument("--asset-type", default="equity")
        parser.add_argument("--exchange", default="")
        parser.add_argument("--currency", default="USD")
        parser.add_argument("--source", default="cli")

    def handle(self, *args: object, **options: object) -> None:
        """Register assets and print a concise summary."""
        payloads = [self._payload(symbol, options) for symbol in options["symbol"]]
        summary = register_assets(payloads, provenance={"source": options["source"]})
        self.stdout.write(
            f"assets={len(summary.assets)} created={summary.created_count} "
            f"updated={summary.updated_count}"
        )

    def _payload(self, symbol: str, options: dict[str, object]) -> dict[str, object]:
        """Build one asset payload from command options."""
        return {
            "symbol": symbol,
            "asset_type": options["asset_type"],
            "exchange": options["exchange"],
            "currency": options["currency"],
        }
