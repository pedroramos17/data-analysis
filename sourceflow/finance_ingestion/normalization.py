"""Shared finance ingestion normalization helpers."""

from __future__ import annotations


def normalize_symbol(symbol: object) -> str:
    """Return an uppercase instrument symbol.

    Example:
        `normalize_symbol(" aapl ") == "AAPL"`
    """
    value = str(symbol).strip().upper()
    if value:
        return value
    raise ValueError(f"Invalid symbol {symbol!r}; expected non-empty text")


def normalize_timeframe(timeframe: object) -> str:
    """Return a compact lower-case market-bar timeframe.

    Example:
        `normalize_timeframe("1D") == "1d"`
    """
    value = str(timeframe).strip().lower()
    if value:
        return value
    raise ValueError(f"Invalid timeframe {timeframe!r}; expected non-empty text")
