"""Import compliant market snapshots and build feature frames."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from monitoring.exporters import ArrowTableWriter
from monitoring.models import MarketBar, MarketInstrument, MarketTick, Source
from sourceflow.intelligence.market.contracts import (
    InstrumentRef,
    MarketBarPoint,
    MarketTickPoint,
)
from sourceflow.intelligence.market.io import (
    MarketSnapshot,
    build_market_intelligence_frame,
    capture_authorized_browser_snapshot,
    read_jsonl_market_snapshot,
    record_type_counts,
    write_jsonl_market_snapshot,
)
from sourceflow.intelligence.market.policy import (
    VENDOR_AUTHORIZED_MODES,
    validate_authorized_vendor_config,
    validate_ingestion_mode,
)


class Command(BaseCommand):
    """Import local or vendor-authorized market snapshot records.

    Example:
        `python manage.py import_market_snapshot --path snapshot.jsonl`
    """

    help = "Import compliant market snapshots and write optional feature frames."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add import options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--path", required=True)
        parser.add_argument("--relation-path")
        parser.add_argument("--mode", required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--output")
        parser.add_argument("--secrets-path")

    def handle(self, *args: object, **options: object) -> None:
        """Run snapshot import and feature-frame generation.

        Example:
            Django calls this after parsing command options.
        """
        mode = _validated_mode(options["mode"])
        config = _vendor_config(options.get("secrets_path"), mode)
        snapshot_path = _prepare_snapshot_path(Path(str(options["path"])), mode, config)
        snapshot = read_jsonl_market_snapshot(snapshot_path)
        rows = build_market_intelligence_frame(
            snapshot_path, _path_or_none(options.get("relation_path"))
        )
        counts = _counts_text(record_type_counts(snapshot))
        if not bool(options.get("dry_run")):
            _persist_snapshot(snapshot, mode)
            _write_output(_path_or_none(options.get("output")), rows)
        self.stdout.write(f"Imported market snapshot counts: {counts}")


def _validated_mode(value: object) -> str:
    try:
        return validate_ingestion_mode(str(value))
    except ValueError as error:
        raise CommandError(str(error)) from error


def _vendor_config(path_value: object, mode: str) -> dict[str, object]:
    if mode not in VENDOR_AUTHORIZED_MODES:
        return {}
    if not path_value:
        raise CommandError(
            f"Invalid --secrets-path {path_value!r}; "
            f"expected local JSON file for {mode}"
        )
    config = _read_secrets_config(Path(str(path_value)))
    _validate_vendor_config(config, mode)
    return config


def _read_secrets_config(path: Path) -> dict[str, object]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except OSError as error:
        raise CommandError(
            f"Invalid --secrets-path {path}; expected readable JSON"
        ) from error
    if not isinstance(value, dict):
        raise CommandError(f"Invalid --secrets-path {path}; expected JSON object")
    return {str(key): item for key, item in value.items()}


def _validate_vendor_config(config: Mapping[str, object], mode: str) -> None:
    try:
        validate_authorized_vendor_config(config, mode)
    except ValueError as error:
        raise CommandError(str(error)) from error


def _prepare_snapshot_path(
    snapshot_path: Path,
    mode: str,
    config: Mapping[str, object],
) -> Path:
    if mode == "vendor_authorized_browser" and not snapshot_path.exists():
        return capture_authorized_browser_snapshot(snapshot_path, config)
    return snapshot_path


def _persist_snapshot(snapshot: MarketSnapshot, mode: str) -> None:
    instruments = _instrument_map(snapshot.instruments)
    for tick in snapshot.ticks:
        _upsert_tick(tick, instruments, mode)
    for bar in snapshot.bars:
        _upsert_bar(bar, instruments, mode)


def _instrument_map(
    instruments: Sequence[InstrumentRef],
) -> dict[tuple[str, str], MarketInstrument]:
    return {
        (instrument.symbol, instrument.exchange): _upsert_instrument(instrument)
        for instrument in instruments
    }


def _upsert_instrument(instrument: InstrumentRef) -> MarketInstrument:
    market_instrument, _created = MarketInstrument.objects.update_or_create(
        symbol=instrument.symbol,
        exchange=instrument.exchange,
        defaults=_instrument_defaults(instrument),
    )
    return market_instrument


def _instrument_defaults(instrument: InstrumentRef) -> dict[str, object]:
    return {
        "asset_class": instrument.asset_class,
        "currency": instrument.currency,
        "country": instrument.country,
        "sector": instrument.sector,
        "industry": instrument.industry,
        "active": True,
    }


def _upsert_tick(
    tick: MarketTickPoint,
    instruments: Mapping[tuple[str, str], MarketInstrument],
    mode: str,
) -> None:
    instrument = _instrument_for_point(tick.instrument, instruments)
    source = _source_for_label(tick.source, mode)
    MarketTick.objects.update_or_create(
        instrument=instrument,
        source=source,
        timestamp=tick.timestamp,
        trade_id=tick.trade_id,
        defaults=_tick_defaults(tick),
    )


def _upsert_bar(
    bar: MarketBarPoint,
    instruments: Mapping[tuple[str, str], MarketInstrument],
    mode: str,
) -> None:
    instrument = _instrument_for_point(bar.instrument, instruments)
    source = _source_for_label(bar.source, mode)
    MarketBar.objects.update_or_create(
        instrument=instrument,
        source=source,
        timestamp=bar.timestamp,
        timeframe=bar.timeframe,
        defaults=_bar_defaults(bar),
    )


def _instrument_for_point(
    instrument: InstrumentRef,
    instruments: Mapping[tuple[str, str], MarketInstrument],
) -> MarketInstrument:
    key = (instrument.symbol, instrument.exchange)
    return instruments.get(key) or _upsert_instrument(instrument)


def _source_for_label(label: str, mode: str) -> Source:
    source_label = label.strip() or mode
    source, _created = Source.objects.get_or_create(
        name=f"Market Snapshot: {source_label}"[:180],
        defaults=_source_defaults(source_label, mode),
    )
    return source


def _source_defaults(source_label: str, mode: str) -> dict[str, object]:
    return {
        "url": f"https://example.local/sourceflow/{source_label}",
        "source_type": Source.SourceType.API,
        "fetch_method": Source.FetchMethod.API,
        "category": Source.Category.MARKETS,
        "source_kind": Source.SourceKind.OTHER,
        "tags": ["market", mode],
    }


def _tick_defaults(tick: MarketTickPoint) -> dict[str, object]:
    return {
        "price": tick.price,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "volume": tick.volume,
        "dollar_volume": None,
        "raw_payload_json": {},
        "quality_flags_json": {},
    }


def _bar_defaults(bar: MarketBarPoint) -> dict[str, object]:
    return {
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "dollar_volume": bar.dollar_volume,
        "trade_count": bar.trade_count,
        "raw_payload_json": {},
        "quality_flags_json": {},
    }


def _write_output(path: Path | None, rows: list[dict[str, object]]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        ArrowTableWriter().write_parquet(rows, path)
    elif path.suffix == ".csv":
        _write_csv_output(path, rows)
    elif path.suffix == ".jsonl":
        write_jsonl_market_snapshot(path, rows)
    else:
        raise CommandError(
            f"Invalid --output {path}; expected .parquet, .csv, or .jsonl"
        )


def _write_csv_output(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _path_or_none(value: object) -> Path | None:
    if not value:
        return None
    return Path(str(value))


def _counts_text(counts: Mapping[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in counts.items())
