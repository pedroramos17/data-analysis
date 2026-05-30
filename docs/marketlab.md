# MarketLab

MarketLab lives under `quant4/services/marketlab/`. It is an experimental
service package inside Quant4, not a separate Django app.

MarketLab uses shared Quant4 models:

- `WindowArtifact` for prepared windows.
- `GraphSnapshot` for graph outputs.
- `ModelRun` for benchmarks.
- `BacktestRun` and `ExplainabilityReport` for later research reports.

Persisted MarketLab runs must populate the shared reproducibility fields:
`config_hash`, `random_seed`, data range, split range, `feature_schema_json`,
and `provenance_json`. Feature schemas should describe inputs and claim scope so
benchmarks and graph outputs remain research metadata, not validity or
profitability claims.

It must not create competing `Experiment`, `WindowArtifact`, `GraphSnapshot`, or
`ModelRun` tables. New persistence should use the shared Quant4 records unless a
future ADR explicitly justifies another model.

Commands:

```bash
python manage.py marketlab_prepare_windows --values-json "[1,2,3,4,5,6]"
python manage.py marketlab_validate_shuffles --values-json "[1,2,3,4]"
python manage.py marketlab_detect_regimes --values-json "[1,2,3,4]"
python manage.py marketlab_run_benchmark --predictions-json "[1,0]" --labels-json "[1,1]" --data-start 2024-01-01 --data-end 2024-01-02 --split-start 2024-01-02 --split-end 2024-01-02
```
