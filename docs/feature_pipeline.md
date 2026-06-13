# Feature Pipeline

The Phase 5 feature pipeline builds versioned feature sets from bronze/silver
Parquet. It reads with DuckDB when available, avoids pandas, and keeps a
deterministic local fallback for dependency-light mock files.

## CLI

```powershell
python -m src.cli features build --config configs/features.yaml
```

Default output layout:

```text
data/lake/features/
  feature_set={name}/
  version={version}/
  symbol={symbol}/
  timeframe={timeframe}/
  part-000.parquet
```

## Feature Groups

- `price_volume`: log return, simple return, rolling mean, rolling volatility,
  realized volatility, momentum, mean reversion, rolling z-score, drawdown,
  volume z-score, liquidity proxy.
- `lob`: spread, mid price, microprice, order/depth imbalance, slope, queue
  pressure, bid/ask slope, short-horizon volatility.
- `multifractal`: rolling generalized Hurst proxy, MF-DFA proxy, spectrum width,
  intermittency, scaling exponent, multifractal volatility, market inefficiency.
- `regime`: volatility, trend, correlation, liquidity, multifractal
  inefficiency regimes.
- `risk`: VaR, CVaR, max drawdown, rolling beta, rolling correlation,
  covariance estimate, tail-risk flags.
- `graph`: correlation-degree, market-centrality, sector/event relation, and
  graph-embedding placeholders.

## Metadata

Each feature-set output registers a row in `feature_runs` with the feature set,
version, input URI, output URI, config, rows, columns, timing, status, and
`error_json`.

The CLI result reports runtime seconds, memory MB, row throughput, input row
count, output row count, and `no_future_leakage=true`. Rolling windows use only
past and current rows ordered by symbol/timeframe/timestamp.
