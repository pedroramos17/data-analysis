# Efficiency Report: pipeline_run_4

## Summary
- Task count: 11
- Wall-clock seconds: 1.650361
- CPU seconds: 0.050823
- Peak memory MB: 692.347656
- Rows/sec: 0.0
- Estimated cloud cost USD: 0.0

## Slowest Tasks
- ingest_raw: 1.020746s
- train_neural_optional: 0.070935s
- build_sliding_windows: 0.067497s
- train_baselines: 0.066869s
- aggregate_report: 0.064941s

## Quality Gates
- max_pipeline_minutes_local: PASS (actual=0.027506, limit=30.0)
- max_peak_memory_mb: PASS (actual=692.347656, limit=4096.0)
- min_rows_per_second: PASS (actual=0.0, limit=10000.0)
- max_gpu_job_minutes: PASS (actual=0.017012, limit=60.0)
- max_cost_per_run_usd: PASS (actual=0.0, limit=2.0)

## Recommendations
- Optimize slowest tasks first: ingest_raw, train_neural_optional, build_sliding_windows.
- No cloud cost recorded; local/offline execution remains within budget-first defaults.
