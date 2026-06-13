"""Limit-order-book ingestion sources."""

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
class LobDataSource:
    """Local/mock LOB snapshot source for no-network ingestion tests."""

    config: Mapping[str, object]
    name: str = field(init=False)
    schema_type: str = "lob"
    _rows: list[dict[str, object]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.name = str(self.config.get("source") or "sample_lob")
        self._rows = configured_rows(self.config)

    def discover_assets(self) -> list[SourceAsset]:
        """Discover symbols from config or local LOB rows."""
        asset_type = str(self.config.get("asset_type") or "equity")
        timeframe = str(self.config.get("timeframe") or "tick")
        return [
            SourceAsset(symbol, asset_type, timeframe)
            for symbol in configured_symbols(self.config, self._rows)
        ]

    def fetch_raw_data(self, asset: SourceAsset) -> RawIngestionBatch:
        """Fetch inline/local rows or deterministic no-network LOB rows."""
        rows = rows_for_symbol(self._rows, asset.symbol) if self._rows else []
        if not rows:
            rows = _sample_lob_rows(self.config, asset, self.name)
        return RawIngestionBatch(asset, rows)


def _sample_lob_rows(
    config: Mapping[str, object],
    asset: SourceAsset,
    source: str,
) -> list[dict[str, object]]:
    start = datetime.fromisoformat(str(config.get("start") or "2024-01-01T09:30:00"))
    periods = int(config.get("periods") or config.get("limit") or 5)
    rows: list[dict[str, object]] = []
    for index in range(max(periods, 0)):
        ts = start + timedelta(seconds=index)
        mid = 100.0 + index * 0.01
        rows.append(
            {
                "source": source,
                "asset_type": asset.asset_type,
                "symbol": asset.symbol,
                "timeframe": asset.timeframe,
                "ts": ts.isoformat(),
                "bid_price_1": mid - 0.01,
                "bid_size_1": 100 + index,
                "ask_price_1": mid + 0.01,
                "ask_size_1": 120 + index,
            }
        )
    return rows
