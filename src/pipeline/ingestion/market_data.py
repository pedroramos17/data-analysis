"""Market data ingestion sources."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.pipeline.ingestion.source_base import (
    RawIngestionBatch,
    SourceAsset,
    configured_rows,
    configured_symbols,
    rows_for_symbol,
)


@dataclass(slots=True)
class MarketDataSource:
    """Local/mock OHLCV market-data source.

    Example:
        `MarketDataSource({"symbols": ["SPY"]}).discover_assets()`
    """

    config: Mapping[str, object]
    name: str = field(init=False)
    schema_type: str = "market"
    _rows: list[dict[str, object]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.name = str(self.config.get("source") or "sample")
        self._rows = configured_rows(self.config)

    def discover_assets(self) -> list[SourceAsset]:
        """Discover symbols from config or local rows."""
        asset_type = str(self.config.get("asset_type") or "equity")
        timeframe = str(self.config.get("timeframe") or "1d")
        return [
            SourceAsset(symbol, asset_type, timeframe)
            for symbol in configured_symbols(self.config, self._rows)
        ]

    def fetch_raw_data(self, asset: SourceAsset) -> RawIngestionBatch:
        """Fetch inline/local rows or deterministic no-network sample rows."""
        rows = rows_for_symbol(self._rows, asset.symbol) if self._rows else []
        if not rows:
            rows = _sample_market_rows(self.config, asset, self.name)
        return RawIngestionBatch(asset, rows)


def _sample_market_rows(
    config: Mapping[str, object],
    asset: SourceAsset,
    source: str,
) -> list[dict[str, object]]:
    start = datetime.fromisoformat(str(config.get("start") or "2024-01-01"))
    periods = int(config.get("periods") or config.get("limit") or 5)
    offset = sum(ord(char) for char in asset.symbol) % 30
    rows: list[dict[str, object]] = []
    for index in range(max(periods, 0)):
        ts = start + timedelta(days=index)
        close = 100.0 + offset + index * 0.5
        rows.append(
            {
                "source": source,
                "asset_type": asset.asset_type,
                "symbol": asset.symbol,
                "timeframe": asset.timeframe,
                "ts": ts.isoformat(),
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.6,
                "close": close,
                "volume": 1_000_000 + index * 1_000 + offset,
            }
        )
    return rows
