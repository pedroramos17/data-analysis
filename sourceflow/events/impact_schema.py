"""Auditable impact schema for extracted market events."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

RISK_CHANNELS_BY_EVENT_TYPE = {
    "lawsuit": ("legal_risk", "sentiment_risk"),
    "regulatory_action": ("regulatory_risk", "legal_risk", "sentiment_risk"),
    "supply_chain_disruption": ("supply_chain_risk", "market_risk"),
    "credit_event": ("credit_risk", "liquidity_risk"),
    "commodity_shock": ("commodity_risk", "market_risk"),
    "currency_shock": ("currency_risk", "market_risk"),
    "liquidity_event": ("liquidity_risk", "execution_risk"),
    "lob_anomaly": ("execution_risk", "liquidity_risk"),
    "earnings": ("market_risk", "sentiment_risk"),
    "guidance": ("market_risk", "sentiment_risk"),
}
BASE_MAGNITUDE_BY_POLARITY = {
    "negative": Decimal("-0.30"),
    "positive": Decimal("0.30"),
    "neutral": Decimal("0.00"),
    "unknown": Decimal("0.00"),
}


@dataclass(frozen=True)
class EventImpact:
    """Default impact metadata for an event."""

    event_type: str
    polarity: str
    magnitude: Decimal
    risk_channels: tuple[str, ...]


def default_event_impact(event_type: str, polarity: str) -> EventImpact:
    """Return an auditable default impact schema for an event type."""
    return EventImpact(
        event_type=event_type,
        polarity=polarity,
        magnitude=BASE_MAGNITUDE_BY_POLARITY.get(polarity, Decimal("0.00")),
        risk_channels=RISK_CHANNELS_BY_EVENT_TYPE.get(event_type, ("market_risk",)),
    )
