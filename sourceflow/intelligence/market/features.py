"""Feature builders for Sourceflow market prediction frames."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sourceflow.finance_core.contracts import (
    CompanyRelation,
    InstrumentRef,
    LimitOrderBookSnapshot,
    MarketBarPoint,
    MarketTickPoint,
    OpenOrderFlowSnapshot,
)
from sourceflow.intelligence.market.knowledge_graph import (
    build_company_graph,
    graph_exposure_scores,
)
from sourceflow.intelligence.market.microstructure import (
    dollar_volume,
    microprice,
    mid_price,
    open_order_pressure,
    order_book_imbalance,
    realized_volatility,
    signed_return,
    spread_abs,
    spread_bps,
    weighted_mid_price,
)


def build_tick_features(ticks: Sequence[MarketTickPoint]) -> list[dict[str, object]]:
    """Build tick-level microstructure rows.

    Example:
        `rows = build_tick_features(ticks)`
    """
    return [_tick_row(tick) for tick in ticks]


def build_bar_features(bars: Sequence[MarketBarPoint]) -> list[dict[str, object]]:
    """Build bar-level return, notional, and volatility rows.

    Example:
        `rows = build_bar_features(bars)`
    """
    sorted_bars = sorted(bars, key=_market_time_key)
    close_by_symbol = _close_history(sorted_bars)
    previous_close: dict[str, float] = {}
    return [_bar_row(bar, close_by_symbol, previous_close) for bar in sorted_bars]


def build_lob_features(
    order_books: Sequence[LimitOrderBookSnapshot],
) -> list[dict[str, object]]:
    """Build limit-order-book feature rows.

    Example:
        `rows = build_lob_features(order_books)`
    """
    return [_lob_row(snapshot) for snapshot in order_books]


def build_open_order_features(
    flows: Sequence[OpenOrderFlowSnapshot],
) -> list[dict[str, object]]:
    """Build open-order-flow feature rows.

    Example:
        `rows = build_open_order_features(flows)`
    """
    return [_flow_row(flow) for flow in flows]


def build_knowledge_features(
    instruments: Sequence[InstrumentRef],
    relations: Sequence[CompanyRelation],
    seed_scores: Mapping[str, float],
) -> list[dict[str, object]]:
    """Build graph exposure feature rows.

    Example:
        `rows = build_knowledge_features(instruments, relations, {"BANK": 1})`
    """
    graph = build_company_graph(instruments, relations)
    exposures = graph_exposure_scores(graph, seed_scores)
    return [_knowledge_row(instrument, exposures) for instrument in instruments]


def build_prediction_frame(
    ticks: Sequence[MarketTickPoint] = (),
    bars: Sequence[MarketBarPoint] = (),
    order_books: Sequence[LimitOrderBookSnapshot] = (),
    flows: Sequence[OpenOrderFlowSnapshot] = (),
    instruments: Sequence[InstrumentRef] = (),
    relations: Sequence[CompanyRelation] = (),
    seed_scores: Mapping[str, float] | None = None,
) -> list[dict[str, object]]:
    """Build a knowledge-enriched market prediction frame.

    Example:
        `rows = build_prediction_frame(ticks=ticks, instruments=instruments)`
    """
    market_rows = _market_feature_rows(ticks, bars, order_books, flows)
    knowledge_rows = build_knowledge_features(instruments, relations, seed_scores or {})
    if not market_rows:
        return knowledge_rows
    return [_merge_knowledge(row, knowledge_rows) for row in market_rows]


def to_pandas_frame(rows: Sequence[Mapping[str, object]]) -> object:
    """Return a pandas DataFrame when pandas is installed.

    Example:
        `frame = to_pandas_frame(rows)`
    """
    try:
        import pandas as pd
    except ImportError as error:
        raise RuntimeError(
            "pandas frame failed; expected pandas to be installed"
        ) from error
    return pd.DataFrame(list(rows))


def _tick_row(tick: MarketTickPoint) -> dict[str, object]:
    return _base_row(tick.instrument, tick.timestamp, tick.source) | {
        "record_type": "tick_feature",
        "price": tick.price,
        "bid": tick.bid,
        "ask": tick.ask,
        "last": tick.last,
        "volume": tick.volume,
        "trade_id": tick.trade_id,
        "mid_price": mid_price(tick.bid, tick.ask),
        "spread_abs": spread_abs(tick.bid, tick.ask),
        "spread_bps": spread_bps(tick.bid, tick.ask),
        "dollar_volume": dollar_volume(tick.price or tick.last, tick.volume),
    }


def _bar_row(
    bar: MarketBarPoint,
    close_by_symbol: Mapping[str, list[float | None]],
    previous_close: dict[str, float],
) -> dict[str, object]:
    key = _instrument_key(bar.instrument)
    row = _base_row(bar.instrument, bar.timestamp, bar.source)
    row.update(_bar_payload(bar, close_by_symbol, previous_close.get(key)))
    if bar.close is not None:
        previous_close[key] = bar.close
    return row


def _bar_payload(
    bar: MarketBarPoint,
    close_by_symbol: Mapping[str, list[float | None]],
    previous_close: float | None,
) -> dict[str, object]:
    key = _instrument_key(bar.instrument)
    return {
        "record_type": "bar_feature",
        "timeframe": bar.timeframe,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "trade_count": bar.trade_count,
        "signed_return": signed_return(previous_close, bar.close),
        "realized_volatility": realized_volatility(close_by_symbol.get(key, [])),
        "dollar_volume": bar.dollar_volume or dollar_volume(bar.close, bar.volume),
    }


def _lob_row(snapshot: LimitOrderBookSnapshot) -> dict[str, object]:
    bid = snapshot.bids[0].price if snapshot.bids else None
    ask = snapshot.asks[0].price if snapshot.asks else None
    return _base_row(snapshot.instrument, snapshot.timestamp, snapshot.source) | {
        "record_type": "lob_feature",
        "depth": snapshot.depth,
        "mid_price": mid_price(bid, ask),
        "spread_abs": spread_abs(bid, ask),
        "spread_bps": spread_bps(bid, ask),
        "order_book_imbalance": order_book_imbalance(snapshot),
        "weighted_mid_price": weighted_mid_price(snapshot),
        "microprice": microprice(snapshot),
    }


def _flow_row(flow: OpenOrderFlowSnapshot) -> dict[str, object]:
    return _base_row(flow.instrument, flow.timestamp, flow.source) | {
        "record_type": "open_order_flow_feature",
        "open_order_pressure": open_order_pressure(flow),
        "submitted_buy_volume": flow.submitted_buy_volume,
        "submitted_sell_volume": flow.submitted_sell_volume,
        "cancelled_buy_volume": flow.cancelled_buy_volume,
        "cancelled_sell_volume": flow.cancelled_sell_volume,
        "executed_buy_volume": flow.executed_buy_volume,
        "executed_sell_volume": flow.executed_sell_volume,
    }


def _knowledge_row(
    instrument: InstrumentRef,
    exposures: Mapping[str, float],
) -> dict[str, object]:
    return {
        "record_type": "knowledge_feature",
        "symbol": instrument.symbol,
        "exchange": instrument.exchange,
        "sector": instrument.sector,
        "industry": instrument.industry,
        "graph_exposure_score": exposures.get(instrument.symbol, 0.0),
    }


def _base_row(
    instrument: InstrumentRef,
    timestamp: object,
    source: str,
) -> dict[str, object]:
    return {
        "symbol": instrument.symbol,
        "exchange": instrument.exchange,
        "timestamp": timestamp,
        "source": source,
    }


def _market_feature_rows(
    ticks: Sequence[MarketTickPoint],
    bars: Sequence[MarketBarPoint],
    order_books: Sequence[LimitOrderBookSnapshot],
    flows: Sequence[OpenOrderFlowSnapshot],
) -> list[dict[str, object]]:
    rows = build_tick_features(ticks)
    rows.extend(build_bar_features(bars))
    rows.extend(build_lob_features(order_books))
    rows.extend(build_open_order_features(flows))
    return rows


def _merge_knowledge(
    row: dict[str, object],
    knowledge_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    knowledge_by_symbol = {item["symbol"]: item for item in knowledge_rows}
    knowledge = knowledge_by_symbol.get(row.get("symbol"), {})
    return row | {
        "sector": knowledge.get("sector", ""),
        "industry": knowledge.get("industry", ""),
        "graph_exposure_score": knowledge.get("graph_exposure_score", 0.0),
    }


def _market_time_key(bar: MarketBarPoint) -> tuple[str, str, object]:
    return (bar.instrument.symbol, bar.instrument.exchange, bar.timestamp)


def _instrument_key(instrument: InstrumentRef) -> str:
    return f"{instrument.symbol}:{instrument.exchange}"


def _close_history(bars: Sequence[MarketBarPoint]) -> dict[str, list[float | None]]:
    history: dict[str, list[float | None]] = {}
    for bar in bars:
        key = _instrument_key(bar.instrument)
        history.setdefault(key, []).append(bar.close)
    return history
