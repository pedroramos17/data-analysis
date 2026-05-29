"""Pure microstructure feature functions."""

from __future__ import annotations

from math import sqrt

from sourceflow.intelligence.market.contracts import (
    LimitOrderBookSnapshot,
    OpenOrderFlowSnapshot,
    OrderBookLevel,
)

Number = float | int


def mid_price(bid: Number | None, ask: Number | None) -> float | None:
    """Return the quote midpoint when bid and ask are usable.

    Example:
        `mid_price(99, 101) == 100`
    """
    pair = _quote_pair(bid, ask)
    if pair is None:
        return None
    return (pair[0] + pair[1]) / 2


def spread_abs(bid: Number | None, ask: Number | None) -> float | None:
    """Return absolute spread for a valid quote pair.

    Example:
        `spread_abs(99, 101) == 2`
    """
    pair = _quote_pair(bid, ask)
    if pair is None:
        return None
    return pair[1] - pair[0]


def spread_bps(bid: Number | None, ask: Number | None) -> float | None:
    """Return spread in basis points for a valid quote pair.

    Example:
        `spread_bps(99, 101) == 200`
    """
    midpoint = mid_price(bid, ask)
    spread = spread_abs(bid, ask)
    if midpoint is None or midpoint == 0 or spread is None:
        return None
    return spread / midpoint * 10000


def order_book_imbalance(
    snapshot: LimitOrderBookSnapshot,
    depth: int = 5,
) -> float:
    """Return signed bid/ask size imbalance for the top depth.

    Example:
        `order_book_imbalance(snapshot, depth=3)`
    """
    bid_size = _level_size(snapshot.bids, depth)
    ask_size = _level_size(snapshot.asks, depth)
    total_size = bid_size + ask_size
    if total_size == 0:
        return 0.0
    return (bid_size - ask_size) / total_size


def weighted_mid_price(
    snapshot: LimitOrderBookSnapshot,
    depth: int = 5,
) -> float | None:
    """Return size-weighted price across bid and ask book levels.

    Example:
        `weighted_mid_price(snapshot, depth=5)`
    """
    levels = _top_levels(snapshot.bids, depth) + _top_levels(snapshot.asks, depth)
    weighted_total = sum(level.price * level.size for level in levels if level.size > 0)
    total_size = sum(level.size for level in levels if level.size > 0)
    if total_size == 0:
        return None
    return weighted_total / total_size


def microprice(
    snapshot: LimitOrderBookSnapshot,
    depth: int = 1,
) -> float | None:
    """Return top-of-book microprice weighted by opposite side size.

    Example:
        `microprice(snapshot)`
    """
    bid = _weighted_side(snapshot.bids, depth)
    ask = _weighted_side(snapshot.asks, depth)
    if bid is None or ask is None:
        return None
    bid_price, bid_size = bid
    ask_price, ask_size = ask
    total_size = bid_size + ask_size
    if total_size == 0:
        return None
    return (ask_price * bid_size + bid_price * ask_size) / total_size


def open_order_pressure(flow: OpenOrderFlowSnapshot) -> float:
    """Return signed open-order pressure from buy and sell activity.

    Example:
        `open_order_pressure(flow)`
    """
    buy_pressure = flow.submitted_buy_volume - flow.cancelled_buy_volume
    buy_pressure += flow.executed_buy_volume
    sell_pressure = flow.submitted_sell_volume - flow.cancelled_sell_volume
    sell_pressure += flow.executed_sell_volume
    denominator = _flow_denominator(flow)
    if denominator == 0:
        return 0.0
    return (buy_pressure - sell_pressure) / denominator


def dollar_volume(price: Number | None, volume: Number | None) -> float | None:
    """Return notional volume when price and volume are present.

    Example:
        `dollar_volume(10, 3) == 30`
    """
    if price is None or volume is None:
        return None
    return float(price) * float(volume)


def realized_volatility(prices: list[Number | None]) -> float:
    """Return realized volatility from sequential simple returns.

    Example:
        `realized_volatility([100, 101, 99])`
    """
    returns = _valid_returns(prices)
    if not returns:
        return 0.0
    return sqrt(sum(value * value for value in returns) / len(returns))


def signed_return(prev: Number | None, curr: Number | None) -> float | None:
    """Return signed simple return from previous to current price.

    Example:
        `signed_return(100, 101) == 0.01`
    """
    if prev in (None, 0) or curr is None:
        return None
    return (float(curr) - float(prev)) / float(prev)


def _quote_pair(
    bid: Number | None,
    ask: Number | None,
) -> tuple[float, float] | None:
    if bid is None or ask is None:
        return None
    bid_value = float(bid)
    ask_value = float(ask)
    if bid_value <= 0 or ask_value <= 0 or ask_value < bid_value:
        return None
    return bid_value, ask_value


def _top_levels(levels: list[OrderBookLevel], depth: int) -> list[OrderBookLevel]:
    bounded_depth = max(depth, 0)
    return [level for level in levels[:bounded_depth] if level.size > 0]


def _level_size(levels: list[OrderBookLevel], depth: int) -> float:
    return sum(level.size for level in _top_levels(levels, depth))


def _weighted_side(
    levels: list[OrderBookLevel],
    depth: int,
) -> tuple[float, float] | None:
    valid_levels = _top_levels(levels, depth)
    total_size = sum(level.size for level in valid_levels)
    if total_size == 0:
        return None
    weighted_price = sum(level.price * level.size for level in valid_levels)
    return weighted_price / total_size, total_size


def _flow_denominator(flow: OpenOrderFlowSnapshot) -> float:
    return sum(
        abs(value)
        for value in (
            flow.submitted_buy_volume,
            flow.submitted_sell_volume,
            flow.cancelled_buy_volume,
            flow.cancelled_sell_volume,
            flow.executed_buy_volume,
            flow.executed_sell_volume,
        )
    )


def _valid_returns(prices: list[Number | None]) -> list[float]:
    returns: list[float] = []
    previous = None
    for price in prices:
        current_return = signed_return(previous, price)
        if current_return is not None:
            returns.append(current_return)
        if price is not None:
            previous = price
    return returns
