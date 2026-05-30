# Vendor-Authorized Market Intelligence

Sourceflow's market intelligence layer is designed for compliant market data that
the operator is authorized to use. It turns local or vendor-authorized snapshots
into normalized market features, knowledge-graph exposures, and prediction-frame
rows for later factor mining and modeling.

## Safe Data Sources

Supported ingestion modes:

- `public_api`
- `licensed_api`
- `broker_export`
- `exchange_file`
- `manual_csv`
- `local_jsonl`
- `research_snapshot`
- `vendor_authorized_browser`
- `vendor_oauth`
- `vendor_authorized_proxy`

The implementation does not support proxy rotation for evasion, stealth browser
patches, CAPTCHA handling, cookie extraction, credential harvesting, paywall
bypass, login bypass, or anti-bot circumvention. TradingView-style collection is
limited to vendor-permitted Playwright sessions configured with a local
`storage_state_path` and `capture_url` supplied by the operator.

## Architecture

```text
Compliant Data Sources
  APIs | feeds | broker exports | exchange files | local snapshots
        ↓
Market Raw Layer
  tick, OHLCV, dollar volume, LOB, open-order flow, instrument master
        ↓
Market Feature Layer
  spread, mid, microprice, imbalance, realized volatility, order pressure,
  volume shocks, return windows, liquidity stress
        ↓
Financial Knowledge Graph
  issuer, sector, industry, supplier/customer, owner, lender/borrower,
  index/ETF membership, competitor, banking exposure, country/currency
        ↓
Knowledge-Enriched Factors
  graph exposure, supply-chain shock propagation, banking-complex contagion,
  event/news-to-company propagation, liquidity-risk factors
        ↓
Prediction Frame
  instrument × timestamp × market features × graph features × source/news factors
        ↓
Modeling
  baseline symbolic factors → tree/linear models → TCN/GRU/GNN later
        ↓
Risk / Simulation / XAI
  factor attribution, KG path explanation, stress tests, portfolio constraints
```

## MVP Roadmap

1. Import local JSONL and CSV snapshots.
2. Add licensed and public connector boundaries.
3. Write Parquet feature-store outputs.
4. Propagate company and financial exposure through the knowledge graph.
5. Add optional LightGBM/sklearn baselines later; keep TCN/GNN models future-facing.
6. Generate XAI reports with factor attribution and KG path explanations.

## Example JSONL Records

```jsonl
{"record_type":"instrument","symbol":"AAPL","exchange":"NASDAQ","asset_class":"equity","currency":"USD","country":"US","sector":"Technology","industry":"Hardware"}
{"record_type":"tick","symbol":"AAPL","exchange":"NASDAQ","timestamp":"2026-01-01T00:00:00Z","price":101.0,"bid":100.9,"ask":101.1,"volume":500,"trade_id":"t-1","source":"licensed-feed"}
{"record_type":"bar","symbol":"AAPL","exchange":"NASDAQ","timestamp":"2026-01-01T00:01:00Z","timeframe":"1m","open":100.8,"high":101.2,"low":100.7,"close":101.0,"volume":1200,"source":"licensed-feed"}
{"record_type":"lob","symbol":"AAPL","exchange":"NASDAQ","timestamp":"2026-01-01T00:00:00Z","bids":[{"price":100.9,"size":800,"order_count":3}],"asks":[{"price":101.1,"size":600,"order_count":2}],"depth":1,"source":"licensed-feed"}
{"record_type":"open_order_flow","symbol":"AAPL","exchange":"NASDAQ","timestamp":"2026-01-01T00:00:00Z","submitted_buy_volume":1200,"submitted_sell_volume":900,"cancelled_buy_volume":100,"cancelled_sell_volume":80,"executed_buy_volume":300,"executed_sell_volume":250,"source":"broker-export"}
{"record_type":"relation","source_symbol":"AAPL","target_symbol":"TSM","relation_type":"supplier","weight":0.7,"evidence":"licensed supply-chain dataset","source":"research-snapshot"}
{"record_type":"knowledge_signal","symbol":"AAPL","score":0.8,"source":"event-factor"}
```
