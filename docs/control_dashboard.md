# Multi-Profile Control Dashboard

The dashboard at `/dashboard/` controls local and cloud-planned analytics jobs
without adding Celery, Redis, PyTorch, CuPy, or provider SDKs to the core app.

## Local Workers

Run workers in separate terminals:

```powershell
python manage.py dashboard_worker --profile local_cpu_low --worker-id cpu-1
python manage.py dashboard_worker --profile local_mx350_queue --worker-id mx350-1
python manage.py dashboard_worker --profile local_rtx4060ti --worker-id gpu-1
```

Workers claim queued `PipelineJob` rows, acquire CPU/GPU resource locks, run
validated `manage.py` commands with `shell=False`, and write logs/events.

## Job Templates

Use templates to avoid hand-writing commands:

```powershell
python manage.py create_dashboard_jobs --template local_simple_pipeline --profile local_cpu_low
python manage.py create_dashboard_jobs --template cloud_student_advanced_plan --profile cloud_student --dry-run
```

The local template creates CPU-safe jobs. The MX350 template uses micro-batch
settings. Cloud templates write provider-neutral manifests and default to
budget or approval waiting states.

## Cloud Budget Guard

Cloud jobs require a `CloudBudgetPolicy`. Policies limit estimated total cost,
daily cost, per-job cost, runtime, task allow/deny lists, provider, profile, and
concurrent cloud jobs.

```powershell
python manage.py cloud_budget_summary
python manage.py approve_cloud_job --job-id 123 --approved-by local-admin
python manage.py block_cloud_job --job-id 123 --reason "over budget"
```

No real AWS, GCP, Azure, Kaggle, or Colab execution is launched from the
dashboard v1. Cloud output is a manifest and portable command for external
execution.
