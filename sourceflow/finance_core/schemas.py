"""Schema constants for finance-core row contracts."""

from __future__ import annotations

BAR_SCHEMA_VERSION = "finance_core_bar_v1"
BAR_ROW_FIELDS = (
    "symbol",
    "timestamp",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "asset_class",
    "exchange",
    "currency",
    "source",
    "adjusted_close",
    "metadata",
)
