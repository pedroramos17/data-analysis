"""News ingestion sources."""

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
class NewsDataSource:
    """Local/mock public-news source for no-network ingestion tests."""

    config: Mapping[str, object]
    name: str = field(init=False)
    schema_type: str = "news"
    _rows: list[dict[str, object]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.name = str(self.config.get("source") or "sample_news")
        self._rows = configured_rows(self.config)

    def discover_assets(self) -> list[SourceAsset]:
        """Discover symbols from config or local news rows."""
        timeframe = str(self.config.get("timeframe") or "event")
        return [
            SourceAsset(symbol, "news", timeframe)
            for symbol in configured_symbols(self.config, self._rows)
        ]

    def fetch_raw_data(self, asset: SourceAsset) -> RawIngestionBatch:
        """Fetch inline/local rows or deterministic no-network news rows."""
        rows = rows_for_symbol(self._rows, asset.symbol) if self._rows else []
        if not rows:
            rows = _sample_news_rows(self.config, asset, self.name)
        return RawIngestionBatch(asset, rows)


def _sample_news_rows(
    config: Mapping[str, object],
    asset: SourceAsset,
    source: str,
) -> list[dict[str, object]]:
    start = datetime.fromisoformat(str(config.get("start") or "2024-01-01"))
    periods = int(config.get("periods") or config.get("limit") or 3)
    rows: list[dict[str, object]] = []
    for index in range(max(periods, 0)):
        ts = start + timedelta(hours=index)
        rows.append(
            {
                "source": source,
                "asset_type": "news",
                "symbol": asset.symbol,
                "timeframe": asset.timeframe,
                "ts": ts.isoformat(),
                "headline": f"Sample {asset.symbol} news {index + 1}",
                "url": f"mock://news/{asset.symbol}/{index + 1}",
                "publisher": "mock",
            }
        )
    return rows
