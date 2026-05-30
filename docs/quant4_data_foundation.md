# Quant4 Data Foundation

The Quant4 data foundation starts with local metadata:

- `Asset` records define symbols, asset classes, exchange labels, currency, and
  provenance.
- `MarketDataset` records define dataset source, frequency, row count, date
  range, metadata, and provenance.
- `WindowArtifact` records define leakage-safe split metadata and artifact
  provenance.

The initial services are intentionally small:

- `quant4.services.assets.register_assets`
- `quant4.services.data_ingestion.save_market_dataset_metadata`
- `quant4.services.windows.create_window_artifact`
- `quant4.services.leakage.assert_no_future_feature_timestamps`

Leakage checks reject feature timestamps that occur after their label timestamp.
Future feature, factor, graph, and model stores should keep heavy matrices and
tables outside SQLite and store only metadata plus artifact URIs in Quant4.

Quant4 is research-only. It does not include order placement, account access,
execution adapters, profitability claims, or causal claims.
