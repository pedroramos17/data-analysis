# Evaluation

Evaluation runs prediction, baseline comparison, backtesting metrics, risk metrics, drift checks, and report generation over sliding-window datasets.

## Command

```bash
python3 -m src.cli evaluate run --config configs/evaluate_mvp.yaml
```

## Direct Backtest Command

```bash
python3 -m src.cli backtest run --config configs/backtest_mvp.yaml
```

## What It Does

- Loads train, validation, and test windows.
- Loads a trained model when available or uses baseline-compatible prediction behavior.
- Writes prediction rows through the storage provider.
- Compares model predictions to a baseline.
- Computes backtest-style research metrics.
- Computes risk metrics such as VaR, expected shortfall, volatility, exposure, and drawdown.
- Writes per-window and aggregate Markdown/JSON reports.

## Outputs

```text
data/lake/predictions/model={model}/version={version}/window_id={n}/predictions.parquet
data/lake/reports/evaluation/model={model}/version={version}/window_id={n}/window_report.json
data/lake/reports/evaluation/model={model}/version={version}/evaluation_report.json
```

## Interpretation Boundary

Evaluation reports are for research, forecasting, risk analysis, and pipeline validation. They do not claim trading profitability and do not provide investment advice.
