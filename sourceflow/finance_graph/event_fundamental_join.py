"""Point-in-time joins for market and fundamental features."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime


def join_fundamentals_asof(
    events: Iterable[Mapping[str, object]],
    facts: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Join facts using filed_at availability to avoid lookahead leakage.

    Example:
        `rows = join_fundamentals_asof(events, facts)`
    """
    fact_rows = list(facts)
    return [_join_event(event, fact_rows) for event in events]


def _join_event(
    event: Mapping[str, object],
    facts: list[Mapping[str, object]],
) -> dict[str, object]:
    timestamp = _timestamp(event["timestamp"])
    symbol = str(event.get("symbol", ""))
    available = [fact for fact in facts if _fact_available(fact, symbol, timestamp)]
    return dict(event) | {"fundamental_facts": available}


def _fact_available(
    fact: Mapping[str, object],
    symbol: str,
    timestamp: datetime,
) -> bool:
    same_symbol = str(fact.get("symbol", "")) == symbol
    return same_symbol and _timestamp(fact["filed_at"]) <= timestamp


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
