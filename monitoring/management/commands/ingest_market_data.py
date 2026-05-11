from django.core.management.base import BaseCommand

from monitoring.ingestion_v2 import normalize_bar, normalize_tick
from monitoring.models import MarketBar, MarketInstrument, MarketTick, Source


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--source", required=True)
        parser.add_argument("--symbol", action="append", required=True)
        parser.add_argument("--timeframe", default="1d")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        source = Source.objects.get(name=options["source"])
        for symbol in options["symbol"]:
            inst, _ = MarketInstrument.objects.get_or_create(symbol=symbol, exchange="NASDAQ")
            if options["timeframe"] == "tick":
                tick = normalize_tick({"timestamp": "2026-01-01T00:00:00Z", "price": 100, "volume": 10}, source.name, symbol, inst.exchange)
                if not options["dry_run"]:
                    MarketTick.objects.update_or_create(
                        instrument=inst, source=source, timestamp=tick.timestamp, trade_id=tick.trade_id or "",
                        defaults={"price": tick.price, "volume": tick.volume, "dollar_volume": tick.dollar_volume, "quality_flags_json": tick.quality_flags, "raw_payload_json": tick.raw_payload},
                    )
            else:
                bar = normalize_bar({"timestamp": "2026-01-01T00:00:00Z", "open": 99, "high": 101, "low": 98, "close": 100, "volume": 10}, source.name, symbol, inst.exchange, options["timeframe"])
                if not options["dry_run"]:
                    MarketBar.objects.update_or_create(
                        instrument=inst, source=source, timeframe=bar.timeframe, timestamp=bar.timestamp,
                        defaults={"open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume, "dollar_volume": bar.dollar_volume, "quality_flags_json": bar.quality_flags, "raw_payload_json": bar.raw_payload},
                    )
        self.stdout.write(self.style.SUCCESS("ingest_market_data complete"))
