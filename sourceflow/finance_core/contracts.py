"""Provider-neutral finance records and frame contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Sequence

from sourceflow.finance_core.time import require_datetime


@dataclass(frozen=True, slots=True)
class BarRecord:
    """Canonical OHLCV bar shared by ingestion, datasets, and quant services."""

    symbol: str
    timestamp: datetime
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    asset_class: str | None = None
    exchange: str | None = None
    currency: str | None = None
    source: str = ""
    adjusted_close: float | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """Provider-neutral instrument identity used by finance records."""

    symbol: str
    exchange: str
    asset_class: str = ""
    currency: str = ""
    country: str = ""
    sector: str = ""
    industry: str = ""


@dataclass(frozen=True, slots=True)
class MarketTickPoint:
    """Point-in-time tick or quote observation for an instrument."""

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
    """Point-in-time market bar observation for an instrument."""

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
    """One price level in a limit order book snapshot."""

    price: float
    size: float
    order_count: int | None = None


@dataclass(frozen=True, slots=True)
class LimitOrderBookSnapshot:
    """Top-of-book or depth-limited limit order book snapshot."""

    instrument: InstrumentRef
    timestamp: datetime
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    source: str = ""
    depth: int | None = None


@dataclass(frozen=True, slots=True)
class OpenOrderFlowSnapshot:
    """Aggregated submitted, cancelled, and executed order flow."""

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
    """Directed relation between two instruments or companies."""

    source_symbol: str
    target_symbol: str
    relation_type: str
    weight: float = 1.0
    evidence: str = ""
    source: str = ""


@dataclass(frozen=True, slots=True)
class EventRecord:
    """A dated source event that can be joined to finance records."""

    event_id: str
    timestamp: datetime
    source: str
    event_type: str
    entities: Sequence[str] = ()
    payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FundamentalRecord:
    """Point-in-time fundamental value for an instrument."""

    symbol: str
    as_of: datetime
    metric: str
    value: object
    source: str = ""
    reported_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    """Raw provider payload recorded before normalization."""

    source: str
    captured_at: datetime
    payload: Mapping[str, object]
    source_uri: str = ""


@dataclass(frozen=True, slots=True)
class BronzeDataset:
    """Append-only normalized records with minimal quality checks."""

    dataset_id: str
    rows: Sequence[Mapping[str, object]]
    schema_version: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class SilverPanel:
    """Cleaned point-in-time panel ready for features or labels."""

    panel_id: str
    rows: Sequence[Mapping[str, object]]
    schema_version: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GoldDataset:
    """Leakage-checked dataset consumed by modeling and quant research."""

    dataset_id: str
    features: "FeatureFrame"
    labels: "LabelFrame"
    split_id: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    """Versioned feature rows keyed by symbol and timestamp."""

    frame_id: str
    rows: Sequence[Mapping[str, object]]
    feature_set: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class LabelFrame:
    """Versioned label rows with explicit prediction horizon metadata."""

    frame_id: str
    rows: Sequence[Mapping[str, object]]
    target: str
    horizon: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class ForecastFrame:
    """Model forecast rows emitted by a deterministic run."""

    frame_id: str
    rows: Sequence[Mapping[str, object]]
    model_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SignalFrame:
    """Trading or allocation signals derived from forecasts."""

    frame_id: str
    rows: Sequence[Mapping[str, object]]
    signal_set: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Persistable backtest summary shared by quant engines."""

    run_id: str
    metrics: Mapping[str, object]
    trades_path: str = ""
    equity_curve_path: str = ""
    artifact_uri: str = ""


def bar_to_row(bar: BarRecord) -> dict[str, object]:
    """Convert a canonical bar into an Arrow-friendly row."""

    return {
        "symbol": bar.symbol,
        "timestamp": bar.timestamp,
        "timeframe": bar.timeframe,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "asset_class": bar.asset_class,
        "exchange": bar.exchange,
        "currency": bar.currency,
        "source": bar.source,
        "adjusted_close": bar.adjusted_close,
        "metadata": dict(bar.metadata),
    }


def row_to_bar(row: Mapping[str, object]) -> BarRecord:
    """Convert a row mapping into a canonical bar."""

    return BarRecord(
        symbol=str(row["symbol"]),
        timestamp=require_datetime(row["timestamp"], "timestamp"),
        timeframe=str(row["timeframe"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=_optional_float(row.get("volume")),
        asset_class=_optional_text(row.get("asset_class")),
        exchange=_optional_text(row.get("exchange")),
        currency=_optional_text(row.get("currency")),
        source=str(row.get("source", "")),
        adjusted_close=_optional_float(row.get("adjusted_close")),
        metadata=_metadata(row.get("metadata")),
    )


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _metadata(value: object) -> Mapping[str, object]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError(f"Invalid metadata {value!r}; expected mapping")
