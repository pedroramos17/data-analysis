from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def canonicalize_url(raw_url: str) -> str:
    parts = urlsplit(raw_url.strip())
    if not parts.scheme or not parts.netloc:
        raise ValueError("Expected absolute URL")
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k not in TRACKING_QUERY_KEYS
            and not any(k.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
        ),
        doseq=True,
    )
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, host, path, query, ""))


def build_dedupe_hash(item: dict[str, Any]) -> str:
    canonical_url = (item.get("canonical_url") or "").strip()
    if canonical_url:
        basis = f"url::{canonical_url}"
    elif item.get("external_id"):
        basis = f"sid::{item['source_id']}::eid::{item['external_id']}"
    else:
        date = (item.get("published_at") or "")
        if isinstance(date, datetime):
            date = date.date().isoformat()
        basis = "::".join(
            [
                "title",
                str(item.get("title", "")).strip().lower(),
                str(item.get("publisher", "")).strip().lower(),
                str(date),
            ]
        )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NormalizedMarketTick:
    source_id: str
    symbol: str
    exchange: str
    timestamp: datetime
    price: float | None
    bid: float | None
    ask: float | None
    last: float | None
    volume: float | None
    dollar_volume: float | None
    trade_id: str
    raw_payload: dict[str, Any]
    quality_flags: dict[str, Any]


@dataclass(frozen=True)
class NormalizedMarketBar:
    source_id: str
    symbol: str
    exchange: str
    timestamp: datetime
    timeframe: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adjusted_close: float | None
    volume: float | None
    dollar_volume: float | None
    trade_count: int | None
    raw_payload: dict[str, Any]
    quality_flags: dict[str, Any]


def normalize_tick(payload: dict[str, Any], source_id: str, symbol: str, exchange: str) -> NormalizedMarketTick:
    price = _float_or_none(payload.get("price") or payload.get("last"))
    volume = _float_or_none(payload.get("volume"))
    dollar_volume = _float_or_none(payload.get("dollar_volume"))
    quality = {"dollar_volume_source": "provided"}
    if dollar_volume is None and price is not None and volume is not None:
        dollar_volume = price * volume
        quality["dollar_volume_source"] = "computed"
    ts = _parse_ts(payload.get("timestamp"))
    return NormalizedMarketTick(source_id, symbol, exchange, ts, price, _float_or_none(payload.get("bid")), _float_or_none(payload.get("ask")), _float_or_none(payload.get("last")), volume, dollar_volume, str(payload.get("trade_id") or ""), payload, quality)


def normalize_bar(payload: dict[str, Any], source_id: str, symbol: str, exchange: str, timeframe: str) -> NormalizedMarketBar:
    close = _float_or_none(payload.get("close"))
    volume = _float_or_none(payload.get("volume"))
    dollar_volume = _float_or_none(payload.get("dollar_volume"))
    quality = {"dollar_volume_source": "provided"}
    if dollar_volume is None and close is not None and volume is not None:
        dollar_volume = close * volume
        quality["dollar_volume_source"] = "computed"
    ts = _parse_ts(payload.get("timestamp"))
    return NormalizedMarketBar(source_id, symbol, exchange, ts, timeframe, _float_or_none(payload.get("open")), _float_or_none(payload.get("high")), _float_or_none(payload.get("low")), close, _float_or_none(payload.get("adjusted_close")), volume, dollar_volume, _int_or_none(payload.get("trade_count")), payload, quality)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
