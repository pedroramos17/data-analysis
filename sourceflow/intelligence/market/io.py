"""JSONL and authorized-browser I/O for market intelligence snapshots."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path

from sourceflow.finance_core.contracts import (
    CompanyRelation,
    InstrumentRef,
    LimitOrderBookSnapshot,
    MarketBarPoint,
    MarketTickPoint,
    OpenOrderFlowSnapshot,
    OrderBookLevel,
)
from sourceflow.intelligence.market.features import build_prediction_frame
from sourceflow.intelligence.market.policy import validate_authorized_vendor_config

SUPPORTED_RECORD_TYPES = frozenset(
    {
        "instrument",
        "tick",
        "bar",
        "lob",
        "open_order_flow",
        "relation",
        "knowledge_signal",
    }
)


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    records: list[dict[str, object]]
    instruments: list[InstrumentRef]
    ticks: list[MarketTickPoint]
    bars: list[MarketBarPoint]
    order_books: list[LimitOrderBookSnapshot]
    flows: list[OpenOrderFlowSnapshot]
    relations: list[CompanyRelation]
    seed_scores: dict[str, float]


def read_jsonl_market_snapshot(path: str | Path) -> MarketSnapshot:
    """Read a JSONL market snapshot into typed contracts.

    Example:
        `snapshot = read_jsonl_market_snapshot("snapshot.jsonl")`
    """
    records = _read_jsonl_records(Path(path))
    return _snapshot_from_records(records)


def write_jsonl_market_snapshot(
    path: str | Path,
    records: Sequence[Mapping[str, object] | object],
) -> Path:
    """Write JSONL market records.

    Example:
        `write_jsonl_market_snapshot("features.jsonl", rows)`
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_json_ready(record), default=str) + "\n")
    return output_path


def build_market_intelligence_frame(
    snapshot_path: str | Path,
    relation_path: str | Path | None = None,
) -> list[dict[str, object]]:
    """Build a prediction frame from one or two JSONL snapshots.

    Example:
        `rows = build_market_intelligence_frame("snapshot.jsonl")`
    """
    snapshot = read_jsonl_market_snapshot(snapshot_path)
    if relation_path is not None:
        snapshot = _merge_relation_snapshot(
            snapshot, read_jsonl_market_snapshot(relation_path)
        )
    return build_prediction_frame(
        ticks=snapshot.ticks,
        bars=snapshot.bars,
        order_books=snapshot.order_books,
        flows=snapshot.flows,
        instruments=snapshot.instruments,
        relations=snapshot.relations,
        seed_scores=snapshot.seed_scores,
    )


def capture_authorized_browser_snapshot(
    output_path: str | Path,
    config: Mapping[str, object],
) -> Path:
    """Capture vendor-permitted JSONL from a configured Playwright session.

    Example:
        `capture_authorized_browser_snapshot("out.jsonl", config)`
    """
    validate_authorized_vendor_config(config, "vendor_authorized_browser")
    text = _read_authorized_browser_text(config)
    records = _records_from_text(text)
    return write_jsonl_market_snapshot(output_path, records)


def record_type_counts(snapshot: MarketSnapshot) -> dict[str, int]:
    """Return counts by input record type.

    Example:
        `counts = record_type_counts(snapshot)`
    """
    counts = Counter(str(record["record_type"]) for record in snapshot.records)
    return dict(sorted(counts.items()))


def _read_jsonl_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line.strip():
                records.append(_decode_jsonl_line(line, line_number, path))
    return records


def _decode_jsonl_line(line: str, line_number: int, path: Path) -> dict[str, object]:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as error:
        raise ValueError(_json_error(path, line_number, line.strip())) from error
    if not isinstance(record, dict):
        raise ValueError(_record_shape_error(path, line_number, record))
    _validate_record_type(record, path, line_number)
    return {str(key): value for key, value in record.items()}


def _snapshot_from_records(records: list[dict[str, object]]) -> MarketSnapshot:
    instruments = _instrument_records(records)
    return MarketSnapshot(
        records=records,
        instruments=_dedupe_instruments(
            instruments + _instruments_from_points(records)
        ),
        ticks=[_tick_record(record) for record in _records_of_type(records, "tick")],
        bars=[_bar_record(record) for record in _records_of_type(records, "bar")],
        order_books=[
            _lob_record(record) for record in _records_of_type(records, "lob")
        ],
        flows=[
            _flow_record(record)
            for record in _records_of_type(records, "open_order_flow")
        ],
        relations=[
            _relation_record(record) for record in _records_of_type(records, "relation")
        ],
        seed_scores=_seed_scores(records),
    )


def _validate_record_type(
    record: Mapping[str, object],
    path: Path,
    line_number: int,
) -> None:
    value = record.get("record_type")
    if value in SUPPORTED_RECORD_TYPES:
        return
    raise ValueError(
        f"Invalid record_type {value!r} in {path}:{line_number}; expected one of "
        f"{sorted(SUPPORTED_RECORD_TYPES)}"
    )


def _instrument_records(records: Sequence[Mapping[str, object]]) -> list[InstrumentRef]:
    return [
        _instrument_record(record)
        for record in records
        if record.get("record_type") == "instrument"
    ]


def _instrument_record(record: Mapping[str, object]) -> InstrumentRef:
    return InstrumentRef(
        symbol=_text(record, "symbol"),
        exchange=_text(record, "exchange"),
        asset_class=_text(record, "asset_class"),
        currency=_text(record, "currency"),
        country=_text(record, "country"),
        sector=_text(record, "sector"),
        industry=_text(record, "industry"),
    )


def _tick_record(record: Mapping[str, object]) -> MarketTickPoint:
    return MarketTickPoint(
        instrument=_instrument_record(record),
        timestamp=_timestamp(record),
        price=_float(record, "price"),
        bid=_float(record, "bid"),
        ask=_float(record, "ask"),
        last=_float(record, "last"),
        volume=_float(record, "volume"),
        trade_id=_text(record, "trade_id"),
        source=_text(record, "source"),
    )


def _bar_record(record: Mapping[str, object]) -> MarketBarPoint:
    return MarketBarPoint(
        instrument=_instrument_record(record),
        timestamp=_timestamp(record),
        timeframe=_text(record, "timeframe") or "1d",
        open=_float(record, "open"),
        high=_float(record, "high"),
        low=_float(record, "low"),
        close=_float(record, "close"),
        volume=_float(record, "volume"),
        dollar_volume=_float(record, "dollar_volume"),
        trade_count=_int(record, "trade_count"),
        source=_text(record, "source"),
    )


def _lob_record(record: Mapping[str, object]) -> LimitOrderBookSnapshot:
    return LimitOrderBookSnapshot(
        instrument=_instrument_record(record),
        timestamp=_timestamp(record),
        bids=_levels(record.get("bids")),
        asks=_levels(record.get("asks")),
        source=_text(record, "source"),
        depth=_int(record, "depth"),
    )


def _flow_record(record: Mapping[str, object]) -> OpenOrderFlowSnapshot:
    return OpenOrderFlowSnapshot(
        instrument=_instrument_record(record),
        timestamp=_timestamp(record),
        submitted_buy_volume=_float(record, "submitted_buy_volume") or 0.0,
        submitted_sell_volume=_float(record, "submitted_sell_volume") or 0.0,
        cancelled_buy_volume=_float(record, "cancelled_buy_volume") or 0.0,
        cancelled_sell_volume=_float(record, "cancelled_sell_volume") or 0.0,
        executed_buy_volume=_float(record, "executed_buy_volume") or 0.0,
        executed_sell_volume=_float(record, "executed_sell_volume") or 0.0,
        source=_text(record, "source"),
    )


def _relation_record(record: Mapping[str, object]) -> CompanyRelation:
    return CompanyRelation(
        source_symbol=_text(record, "source_symbol"),
        target_symbol=_text(record, "target_symbol"),
        relation_type=_text(record, "relation_type"),
        weight=_float(record, "weight") or 1.0,
        evidence=_text(record, "evidence"),
        source=_text(record, "source"),
    )


def _levels(value: object) -> list[OrderBookLevel]:
    if not isinstance(value, list):
        return []
    return [_level(item) for item in value if isinstance(item, dict)]


def _level(record: Mapping[str, object]) -> OrderBookLevel:
    return OrderBookLevel(
        price=_float(record, "price") or 0.0,
        size=_float(record, "size") or 0.0,
        order_count=_int(record, "order_count"),
    )


def _seed_scores(records: Sequence[Mapping[str, object]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for record in _records_of_type(records, "knowledge_signal"):
        scores[_text(record, "symbol")] = _float(record, "score") or 0.0
    return scores


def _instruments_from_points(
    records: Sequence[Mapping[str, object]],
) -> list[InstrumentRef]:
    records_with_symbol = [record for record in records if "symbol" in record]
    return [_instrument_record(record) for record in records_with_symbol]


def _dedupe_instruments(instruments: Sequence[InstrumentRef]) -> list[InstrumentRef]:
    deduped: dict[tuple[str, str], InstrumentRef] = {}
    for instrument in instruments:
        deduped.setdefault((instrument.symbol, instrument.exchange), instrument)
    return list(deduped.values())


def _records_of_type(
    records: Sequence[Mapping[str, object]],
    record_type: str,
) -> list[Mapping[str, object]]:
    return [record for record in records if record.get("record_type") == record_type]


def _merge_relation_snapshot(
    snapshot: MarketSnapshot,
    relation_snapshot: MarketSnapshot,
) -> MarketSnapshot:
    records = snapshot.records + relation_snapshot.records
    return _snapshot_from_records(records)


def _timestamp(record: Mapping[str, object]) -> datetime:
    value = record.get("timestamp")
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _text(record: Mapping[str, object], key: str) -> str:
    value = record.get(key, "")
    if value is None:
        return ""
    return str(value)


def _float(record: Mapping[str, object], key: str) -> float | None:
    value = record.get(key)
    if value in (None, ""):
        return None
    return float(value)


def _int(record: Mapping[str, object], key: str) -> int | None:
    value = record.get(key)
    if value in (None, ""):
        return None
    return int(value)


def _json_ready(record: Mapping[str, object] | object) -> object:
    if is_dataclass(record) and not isinstance(record, type):
        return asdict(record)
    return record


def _records_from_text(text: str) -> list[dict[str, object]]:
    records = [
        _decode_jsonl_line(line, index, Path("<browser>"))
        for index, line in _lines(text)
    ]
    return records


def _lines(text: str) -> list[tuple[int, str]]:
    return [
        (index, line)
        for index, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]


def _read_authorized_browser_text(config: Mapping[str, object]) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError(
            "Authorized browser capture failed; expected playwright"
        ) from error
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(**_browser_context_args(config))
        page = context.new_page()
        page.goto(_text(config, "capture_url"), wait_until="domcontentloaded")
        text = page.locator("body").inner_text(timeout=10000)
        browser.close()
    return text


def _browser_context_args(config: Mapping[str, object]) -> dict[str, object]:
    args: dict[str, object] = {"storage_state": _text(config, "storage_state_path")}
    proxy_url = _text(config, "proxy_url")
    if proxy_url:
        args["proxy"] = {"server": proxy_url}
    return args


def _json_error(path: Path, line_number: int, line: str) -> str:
    return (
        f"Invalid JSONL record {line!r} in {path}:{line_number}; expected JSON object"
    )


def _record_shape_error(path: Path, line_number: int, record: object) -> str:
    return f"Invalid record {record!r} in {path}:{line_number}; expected JSON object"
