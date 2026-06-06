"""Provider provenance payloads for persisted research runs."""

from __future__ import annotations

from src.config.settings import RuntimeSettings


def build_provider_provenance(settings: RuntimeSettings) -> dict[str, object]:
    """Return non-secret provider metadata for run provenance.

    Example:
        `build_provider_provenance(load_runtime_settings(env={}))`
    """
    return {
        "app_env": settings.app_env,
        "deployment_mode": settings.deployment_mode,
        "database": {"provider": settings.database.db_mode},
        "storage": {
            "provider": settings.storage.provider,
            "remote": settings.storage.uses_remote_object_storage(),
        },
        "warehouse": {"provider": settings.duckdb.olap_mode},
        "queue": {"provider": settings.queue.provider},
        "secrets": {"provider": settings.secrets_provider},
        "model_registry": {"provider": settings.model.provider},
        "compute": {
            "provider": settings.compute.provider,
            "gpu_required": settings.compute.gpu_required,
            "gpu_batch_enabled": settings.compute.gpu_batch_enabled,
        },
        "pipeline": {
            "orchestrator": settings.pipeline.orchestrator,
            "model_device": settings.pipeline.model_device,
            "cost_mode": settings.pipeline.cost_mode,
            "cloud_tests_enabled": settings.pipeline.cloud_tests_enabled,
            "external_paid_api_calls_enabled": settings.pipeline.external_paid_api_calls_enabled,
        },
        "sliding_window": {
            "strategy": settings.sliding_window.strategy,
            "train_size": settings.sliding_window.train_size,
            "validation_size": settings.sliding_window.validation_size,
            "test_size": settings.sliding_window.test_size,
            "step_size": settings.sliding_window.step_size,
            "embargo": settings.sliding_window.embargo,
            "horizon": settings.sliding_window.horizon,
        },
        "runpod": {
            "configured": bool(settings.runpod.api_key),
            "endpoint_url": settings.runpod.endpoint_url,
            "gpu_type": settings.runpod.gpu_type,
            "image": settings.runpod.image,
            "max_runtime_seconds": settings.runpod.max_runtime_seconds,
            "terminate_on_completion": settings.runpod.terminate_on_completion,
            "dry_run": settings.runpod.dry_run,
        },
        "autoscaling": {
            "enabled": settings.autoscaling.enabled,
            "min_workers": settings.autoscaling.min_workers,
            "max_workers": settings.autoscaling.max_workers,
            "max_concurrent_gpu_jobs": settings.autoscaling.max_concurrent_gpu_jobs,
            "max_gpu_workers": settings.autoscaling.max_gpu_workers,
            "max_cpu_workers": settings.autoscaling.max_cpu_workers,
            "queue_check_interval_seconds": settings.autoscaling.queue_check_interval_seconds,
            "scale_to_zero": settings.autoscaling.scale_to_zero,
            "idle_timeout_seconds": settings.autoscaling.idle_timeout_seconds,
            "max_hourly_budget_usd": settings.autoscaling.max_hourly_budget_usd,
            "max_daily_budget_usd": settings.autoscaling.max_daily_budget_usd,
            "prefer_spot": settings.autoscaling.prefer_spot,
            "batch_small_jobs": settings.autoscaling.batch_small_jobs,
        },
        "rate_limit": {
            "provider": settings.rate_limit.provider,
            "requests_per_minute": settings.rate_limit.requests_per_minute,
            "burst": settings.rate_limit.burst,
            "anonymous_requests_per_minute": settings.rate_limit.anonymous_requests_per_minute,
            "authenticated_requests_per_minute": settings.rate_limit.authenticated_requests_per_minute,
            "gpu_submit_requests_per_hour": settings.rate_limit.gpu_submit_requests_per_hour,
            "gpu_submit_requests_per_day": settings.rate_limit.gpu_submit_requests_per_day,
            "ingestion_requests_per_hour": settings.rate_limit.ingestion_requests_per_hour,
            "training_requests_per_hour": settings.rate_limit.training_requests_per_hour,
            "features_requests_per_hour": settings.rate_limit.features_requests_per_hour,
            "predict_requests_per_minute": settings.rate_limit.predict_requests_per_minute,
            "health_requests_per_minute": settings.rate_limit.health_requests_per_minute,
        },
        "efficiency": {
            "enabled": settings.efficiency.enabled,
            "sample_rate": settings.efficiency.sample_rate,
            "record_memory": settings.efficiency.record_memory,
            "record_timing": settings.efficiency.record_timing,
            "output_path": str(settings.efficiency.output_path),
            "report_root": str(settings.efficiency.report_root),
            "max_pipeline_minutes_local": settings.efficiency.max_pipeline_minutes_local,
            "max_peak_memory_mb": settings.efficiency.max_peak_memory_mb,
            "min_rows_per_second": settings.efficiency.min_rows_per_second,
            "max_gpu_job_minutes": settings.efficiency.max_gpu_job_minutes,
            "max_cost_per_run_usd": settings.efficiency.max_cost_per_run_usd,
        },
        "cost_guard": {
            "cost_mode": settings.cost.cost_mode,
            "monthly_budget_usd": settings.cost.monthly_budget_usd,
            "max_job_cost_usd": settings.cost.max_job_cost_usd,
            "max_gpu_hourly_cost_usd": settings.cost.max_gpu_hourly_cost_usd,
            "require_budget_approval": settings.cost.require_budget_approval,
            "external_paid_api_calls_enabled": settings.cost.external_paid_api_calls_enabled,
            "cloud_tests_enabled": settings.cost.cloud_tests_enabled,
        },
        "security": {
            "require_secrets_for_launch": settings.security.require_secrets_for_launch,
            "allow_shell_commands": settings.security.allow_shell_commands,
            "redact_secrets": settings.security.redact_secrets,
            "require_signed_job_manifest": settings.security.require_signed_job_manifest,
            "terminate_remote_on_timeout": settings.security.terminate_remote_on_timeout,
            "api_auth_enabled": settings.security.api_auth_enabled,
            "read_only_requires_auth": settings.security.read_only_requires_auth,
            "api_key_count": len(settings.security.api_key_hashes),
            "cors_allowed_origins": list(settings.security.cors_allowed_origins),
            "max_presigned_url_expiry_seconds": settings.security.max_presigned_url_expiry_seconds,
            "allowed_storage_prefixes": list(settings.security.allowed_storage_prefixes),
        },
    }
