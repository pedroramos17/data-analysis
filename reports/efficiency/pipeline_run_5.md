# Efficiency Report: pipeline_run_5

## Summary
- Task count: 11
- Wall-clock seconds: 2.52054
- CPU seconds: 0.671669
- Peak memory MB: 33.5
- Rows/sec: 0.0
- Estimated cloud cost USD: 0.0

## Slowest Tasks
- ingest_raw: 1.379856s
- extract_features: 0.379813s
- train_baselines: 0.154216s
- preprocess: 0.121662s
- evaluate: 0.102517s

## Quality Gates
- max_pipeline_minutes_local: PASS (actual=0.042009, limit=30.0)
- max_peak_memory_mb: PASS (actual=33.5, limit=4096.0)
- min_rows_per_second: PASS (actual=0.0, limit=10000.0)
- max_gpu_job_minutes: PASS (actual=0.022998, limit=60.0)
- max_cost_per_run_usd: PASS (actual=0.0, limit=2.0)

## Recommendations
- Optimize slowest tasks first: ingest_raw, extract_features, train_baselines.
- No cloud cost recorded; local/offline execution remains within budget-first defaults.
