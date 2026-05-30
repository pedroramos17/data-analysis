# MarketLab

MarketLab lives under `quant4/services/marketlab/`. It is an experimental
service package inside Quant4, not a separate Django app.

MarketLab uses shared Quant4 models:

- `WindowArtifact` for prepared windows.
- `GraphSnapshot` for graph outputs.
- `ModelRun` for benchmarks.
- `BacktestRun` and `ExplainabilityReport` for later research reports.

It must not create competing `Experiment`, `WindowArtifact`, `GraphSnapshot`, or
`ModelRun` tables. New persistence should use the shared Quant4 records unless a
future ADR explicitly justifies another model.

Commands:

```bash
python manage.py marketlab_prepare_windows --values-json "[1,2,3,4,5,6]"
python manage.py marketlab_validate_shuffles --values-json "[1,2,3,4]"
python manage.py marketlab_detect_regimes --values-json "[1,2,3,4]"
python manage.py marketlab_run_benchmark --predictions-json "[1,0]" --labels-json "[1,1]"
```
