# Quant4 Portfolio Optimization

Quant4 portfolio services live under `quant4/services/portfolio/` and persist
research runs through the shared `PortfolioRun` model. The MVP is local-first,
CPU-only, and does not include broker connectivity or live execution.

Implemented local optimizers:

- equal weight
- inverse volatility
- minimum variance from covariance/risk outputs
- max Sharpe prototype

Optional backends:

- HRP
- CVXPY / CVaR
- Riskfolio
- PyPortfolioOpt

Optional backend wrappers raise clear dependency errors when their packages are
missing. Heavy optimizer libraries stay behind feature flags and are not
required for the local MVP.

Constraints include long-only, max weight, sector/country/currency/asset-class
exposure, turnover, liquidity, and transaction cost drag. Outputs are research
metadata only: `weights_path`, `trades_path`, `metrics_json`, and
`risk_report_json`.

```bash
python manage.py quant4_optimize_portfolio --symbols AAA,BBB --optimizer equal_weight --data-start 2024-01-01 --data-end 2024-01-31 --split-start 2024-01-31 --split-end 2024-01-31
```
