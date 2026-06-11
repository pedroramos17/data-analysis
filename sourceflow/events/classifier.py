"""Market event classification helpers."""

from __future__ import annotations

import re

EVENT_KEYWORDS = {
    "earnings": {"earnings", "profit", "revenue", "eps", "reports"},
    "guidance": {"guidance", "forecast", "forecasts", "expects", "signals"},
    "lawsuit": {"lawsuit", "sues", "sued", "settles", "litigation"},
    "regulatory_action": {"regulatory", "regulator", "investigation", "probe", "sanction", "sec", "cvm"},
    "merger_acquisition": {"acquires", "acquisition", "merger", "takeover"},
    "supply_chain_disruption": {"supply", "supplier", "shortage", "disruption"},
    "product_launch": {"launch", "launches", "product"},
    "executive_change": {"ceo", "cfo", "resigns", "appoints", "executive"},
    "credit_event": {"default", "credit", "downgrade", "debt"},
    "macro_event": {"fed", "inflation", "rates", "rate", "gdp", "macro"},
    "commodity_shock": {"oil", "iron", "ore", "commodity", "copper"},
    "currency_shock": {"currency", "fx", "dollar", "real", "yen", "euro"},
    "geopolitical_event": {"war", "election", "sanction", "geopolitical"},
    "analyst_revision": {"analyst", "upgrade", "downgrade", "target"},
    "insider_transaction": {"insider", "buyback", "selling", "purchase"},
    "liquidity_event": {"liquidity", "volume", "spread"},
    "lob_anomaly": {"orderbook", "order", "book", "imbalance", "lob"},
}


def classify_event_type(predicate: str, object_text: str, evidence_text: str = "") -> str:
    """Classify a market event type from structured tuple text."""
    predicate_tokens = set(re.findall(r"[a-z0-9_]+", predicate.lower()))
    context_tokens = set(re.findall(r"[a-z0-9_]+", f"{object_text} {evidence_text}".lower()))
    best_type = "other"
    best_score = 0
    for event_type, keywords in EVENT_KEYWORDS.items():
        score = (2 * len(predicate_tokens & keywords)) + len(context_tokens & keywords)
        if score > best_score:
            best_type = event_type
            best_score = score
    return best_type
