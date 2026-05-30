"""Typed contracts for compliant market intelligence snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    symbol: str
    exchange: str
    asset_class: str = ""
    currency: str = ""
    country: str = ""
    sector: str = ""
    industry: str = ""


@dataclass(frozen=True, slots=True)
class MarketTickPoint:
    instrument: InstrumentRef
    timestamp: datetime
    price: float | None = None
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    volume: float | None = None
    trade_id: str = ""
    source: str = ""


@dataclass(frozen=True, slots=True)
class MarketBarPoint:
    instrument: InstrumentRef
    timestamp: datetime
    timeframe: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    dollar_volume: float | None = None
    trade_count: int | None = None
    source: str = ""


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    size: float
    order_count: int | None = None


@dataclass(frozen=True, slots=True)
class LimitOrderBookSnapshot:
    instrument: InstrumentRef
    timestamp: datetime
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    source: str = ""
    depth: int | None = None


@dataclass(frozen=True, slots=True)
class OpenOrderFlowSnapshot:
    instrument: InstrumentRef
    timestamp: datetime
    submitted_buy_volume: float = 0.0
    submitted_sell_volume: float = 0.0
    cancelled_buy_volume: float = 0.0
    cancelled_sell_volume: float = 0.0
    executed_buy_volume: float = 0.0
    executed_sell_volume: float = 0.0
    source: str = ""


@dataclass(frozen=True, slots=True)
class CompanyRelation:
    source_symbol: str
    target_symbol: str
    relation_type: str
    weight: float = 1.0
    evidence: str = ""
    source: str = ""
