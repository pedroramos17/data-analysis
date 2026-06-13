# Efficiency Report: pipeline_run_3

## Summary
- Task count: 11
- Wall-clock seconds: 2.27018
- CPU seconds: 0.047371
- Peak memory MB: 692.347656
- Rows/sec: 0.0
- Estimated cloud cost USD: 0.0

## Slowest Tasks
- ingest_raw: 1.086893s
- preprocess: 0.707701s
- aggregate_report: 0.062568s
- train_baselines: 0.05834s
- train_neural_optional: 0.054685s

## Quality Gates
- max_pipeline_minutes_local: PASS (actual=0.037836, limit=30.0)
- max_peak_memory_mb: PASS (actual=692.347656, limit=4096.0)
- min_rows_per_second: PASS (actual=0.0, limit=10000.0)
- max_gpu_job_minutes: PASS (actual=0.018115, limit=60.0)
- max_cost_per_run_usd: PASS (actual=0.0, limit=2.0)

## Recommendations
- Optimize slowest tasks first: ingest_raw, preprocess, aggregate_report.
- No cloud cost recorded; local/offline execution remains within budget-first defaults.
