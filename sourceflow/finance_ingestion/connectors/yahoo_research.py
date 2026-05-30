"""Feature-flagged yfinance-like research connector."""

from __future__ import annotations

from sourceflow.config.feature_flags import require_feature


def ingest_yahoo_research(symbols: list[str]) -> list[dict[str, object]]:
    """Build a research ingestion plan for yfinance-like interfaces.

    Example:
        `rows = ingest_yahoo_research(["AAPL"])`
    """
    require_feature("FIN_DATA_YAHOO_RESEARCH")
    return [{"symbol": symbol, "source_type": "yfinance_like"} for symbol in symbols]
