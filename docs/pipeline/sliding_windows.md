# Sliding Windows

Sliding-window dataset construction creates leakage-aware train, validation, and test splits for time-series modeling.

## Command

```bash
python3 -m src.cli windows build --config configs/sliding_window_mvp.yaml
```

## Required Policy

```yaml
sliding_window:
  mode: rolling
  train_size_days: 730
  validation_size_days: 90
  test_size_days: 90
  step_size_days: 30
  embargo_days: 5
  horizon_days: 5
  purge_overlap: true
```

## What It Does

- Reads feature or silver rows from the configured input path.
- Sorts by symbol and timestamp.
- Builds rolling, expanding, purged, or embargoed split definitions.
- Enforces embargo and purge settings before writing windows.
- Writes `train.parquet`, `validation.parquet`, `test.parquet`, and `metadata.json` per window.
- Reports diagnostics for future leakage, embargo violations, horizon compliance, and minimum samples.

## Output Layout

```text
data/lake/datasets/dataset={dataset_name}/version={version}/window_id={n}/train.parquet
data/lake/datasets/dataset={dataset_name}/version={version}/window_id={n}/validation.parquet
data/lake/datasets/dataset={dataset_name}/version={version}/window_id={n}/test.parquet
data/lake/datasets/dataset={dataset_name}/version={version}/window_id={n}/metadata.json
```

## Local Smoke Note

`configs/sliding_window.yaml` is smoke-sized for fast local tests. `configs/sliding_window_mvp.yaml` documents the production-like MVP policy from this phase.
