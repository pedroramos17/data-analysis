# Code Efficiency Observability

Efficiency reporting records task runtime, CPU time, memory, GPU metadata when available, row throughput, estimated cloud cost, quality gates, and recommendations.

## Commands

```bash
python3 -m src.cli pipeline run --config configs/pipeline_local_mvp.yaml
python3 -m src.cli efficiency report --run-id 1
make efficiency-report RUN_ID=1
```

## Report Paths

```text
reports/efficiency/pipeline_run_{run_id}.json
reports/efficiency/pipeline_run_{run_id}.md
data/lake/metrics/efficiency.jsonl
```

## Quality Gates

- `max_pipeline_minutes_local`
- `max_peak_memory_mb`
- `min_rows_per_second`
- `max_gpu_job_minutes`
- `max_cost_per_run_usd`

## Example Output Shape

```json
{
  "run_id": 1,
  "status": "COMPLETED",
  "report": {
    "quality_gates_passed": true,
    "summary": {
      "task_count": 11,
      "estimated_cloud_cost_usd": 0.0
    }
  }
}
```

## Notes

- Reports are redacted through the shared secret redaction helper.
- Missing optional GPU tooling degrades gracefully.
- A zero cloud-cost local run is expected for MVP smoke testing.
