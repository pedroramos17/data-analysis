"""Provider-backed API handler functions independent of FastAPI."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from src.api.jobs import submit_api_job
from src.api.repository import get_backtest, get_risk, list_assets, list_signals
from src.config.settings import load_runtime_settings
from src.cost import estimate_costs
from src.features.pipeline import build_feature_store
from src.models.inference.batch_predict import prediction_rows, run_batch_prediction
from src.models.registry import build_default_model_registry
from src.orchestration import LocalPipelineRunner, PipelineStateStore
from src.pipeline.training import submit_runpod_training_job
from src.providers.provenance import build_provider_provenance
from src.providers.registry import ProviderRegistry, build_provider_registry
from src.security.audit_log import audit_gpu_cancel, audit_gpu_submit
from src.security.validation import validate_storage_key, validate_uploaded_config


def default_registry() -> ProviderRegistry:
    """Build the default provider registry for request handling."""
    return build_provider_registry(load_runtime_settings())


def health(registry: ProviderRegistry) -> dict[str, object]:
    """Return API and provider health without leaking credentials."""
    checks = {
        "db": _safe_check(lambda: registry.get_db().healthcheck()),
        "queue": _safe_check(lambda: registry.get_queue().healthcheck()),
        "storage": _safe_check(lambda: registry.get_storage().list("") is not None),
    }
    status = "ok" if all(check["ok"] for check in checks.values()) else "degraded"
    return {"status": status, "checks": checks}


def runtime_config(registry: ProviderRegistry) -> dict[str, object]:
    """Return non-secret runtime provider configuration."""
    return build_provider_provenance(registry.settings)


def pipeline_runs(registry: ProviderRegistry, *, limit: int = 50, status: str = "") -> dict[str, object]:
    """Return recent persisted pipeline runs."""
    state = PipelineStateStore.from_settings(registry.settings)
    runs = state.list_runs(limit=limit, status=status)
    return {"items": [run.to_dict() for run in runs], "count": len(runs)}


def pipeline_run(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Submit a full pipeline run through orchestration."""
    config = _pipeline_payload(payload)
    return _submit_orchestrated_run(registry, validate_uploaded_config(config, registry.settings), sync=_sync_requested(payload))


def pipeline_dry_run(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Return an orchestration DAG dry-run without creating state."""
    config = validate_uploaded_config(_pipeline_payload(payload), registry.settings)
    plan = LocalPipelineRunner(registry).dry_run(config)
    return {"status": "DRY_RUN", "run_id": None, **plan}


def ingest_run(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Submit an ingestion run through orchestration."""
    return _submit_task_run(registry, "api_ingest_run", "ingest_raw", "ingest", payload)


def preprocess_run(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Submit a preprocessing run through orchestration."""
    return _submit_task_run(registry, "api_preprocess_run", "preprocess", "preprocess", payload)


def features_build(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Build or enqueue the versioned feature store through orchestration."""
    return _submit_task_run(registry, "api_features_build", "extract_features", "features", payload)


def windows_build(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Submit sliding-window dataset construction through orchestration."""
    return _submit_task_run(registry, "api_windows_build", "build_sliding_windows", "windows", payload)


def train_run(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Submit training through orchestration."""
    return _submit_task_run(registry, "api_train_run", "train_baselines", "train", payload)


def evaluate_run(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Submit evaluation through orchestration."""
    return _submit_task_run(registry, "api_evaluate_run", "evaluate", "evaluate", payload)


def models_train(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Train a small registered model synchronously or enqueue a train manifest."""
    return submit_api_job(
        registry,
        "models.train",
        payload,
        sync=_sync_requested(payload),
        handler=lambda job_payload: _train_model_result(registry, job_payload),
    )


def models_predict(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Run small model prediction synchronously or enqueue a predict manifest."""
    return submit_api_job(
        registry,
        "models.predict",
        payload,
        sync=_sync_requested(payload),
        handler=lambda job_payload: _predict_model_result(job_payload),
    )


def backtest_run(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Submit a backtest run through orchestration."""
    return _submit_task_run(registry, "api_backtest_run", "backtest", "backtest", payload)


def cost_estimate(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Return a dependency-light cost estimate."""
    config = validate_uploaded_config(dict(payload), registry.settings)
    return estimate_costs(config, registry.settings).to_dict()


def risk_run(registry: ProviderRegistry, payload: Mapping[str, object]) -> dict[str, object]:
    """Submit a risk-run manifest."""
    return submit_api_job(registry, "risk.run", payload, sync=False)


def compute_runpod_submit(
    registry: ProviderRegistry,
    payload: Mapping[str, object],
    *,
    principal: str = "api",
) -> dict[str, object]:
    """Submit a RunPod GPU job from the API after validation and audit."""
    config = validate_uploaded_config(payload, registry.settings)
    confirm_cost = _bool(config.get("confirm_cost"), False)
    dry_run = _bool(config.get("dry_run"), False)
    state = PipelineStateStore.from_settings(registry.settings)
    run = state.create_run("api_compute_runpod_submit", _compute_run_config("api_compute_runpod_submit", config))
    audit_gpu_submit(registry.settings, principal=principal, status="started", metadata=config)
    try:
        result = submit_runpod_training_job(config, registry, confirm_cost=confirm_cost, dry_run=dry_run)
    except Exception as exc:
        state.update_run_status(run.id, "FAILED", error={"type": type(exc).__name__, "message": str(exc)})
        audit_gpu_submit(registry.settings, principal=principal, status="failed", metadata={"error": str(exc), "config": config})
        raise
    audit_gpu_submit(registry.settings, principal=principal, status=str(result.get("status", "submitted")), metadata=result)
    final_run = state.update_run_status(run.id, "COMPLETED")
    return {"run_id": run.id, "status": str(result.get("status", final_run.status)), "run": final_run.to_dict(), "submission": result}


def compute_runpod_dry_run(
    registry: ProviderRegistry,
    payload: Mapping[str, object],
    *,
    principal: str = "api",
) -> dict[str, object]:
    """Build a dry-run RunPod manifest and record a pipeline run id."""
    config = validate_uploaded_config({**dict(payload), "dry_run": True}, registry.settings)
    state = PipelineStateStore.from_settings(registry.settings)
    run = state.create_run("api_compute_runpod_dry_run", _compute_run_config("api_compute_runpod_dry_run", config))
    result = submit_runpod_training_job(config, registry, dry_run=True)
    final_run = state.update_run_status(run.id, "COMPLETED")
    return {"run_id": run.id, "status": str(result.get("status", final_run.status)), "run": final_run.to_dict(), "submission": result}


def compute_runpod_cancel(
    registry: ProviderRegistry,
    payload: Mapping[str, object],
    *,
    principal: str = "api",
) -> dict[str, object]:
    """Cancel a RunPod GPU job from the API after audit logging."""
    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("compute runpod cancel requires job_id")
    state = PipelineStateStore.from_settings(registry.settings)
    run = state.create_run("api_compute_runpod_cancel", _compute_run_config("api_compute_runpod_cancel", {"job_id": job_id}))
    audit_gpu_cancel(registry.settings, principal=principal, status="started", job_id=job_id, metadata={})
    submission = registry.get_compute().cancel_job(job_id)
    result = {"job_id": submission.job_id, "status": submission.status, "metadata": submission.metadata}
    audit_gpu_cancel(registry.settings, principal=principal, status=submission.status, job_id=job_id, metadata=result)
    final_run = state.update_run_status(run.id, "COMPLETED")
    return {"run_id": run.id, "status": submission.status, "run": final_run.to_dict(), **result}


def efficiency(registry: ProviderRegistry, run_id: int) -> dict[str, object]:
    """Return persisted efficiency payload for a pipeline run."""
    run = PipelineStateStore.from_settings(registry.settings).get_run(run_id)
    return {"run_id": run.id, "status": run.status, "efficiency": dict(run.efficiency_json)}


def reports(registry: ProviderRegistry, run_id: int) -> dict[str, object]:
    """Return report paths and task artifacts for a pipeline run."""
    state = PipelineStateStore.from_settings(registry.settings)
    run = state.get_run(run_id)
    tasks = state.list_tasks(run_id)
    efficiency_payload = dict(run.efficiency_json)
    report_paths = efficiency_payload.get("report_paths") if isinstance(efficiency_payload.get("report_paths"), Mapping) else {}
    return {
        "run_id": run.id,
        "status": run.status,
        "reports": dict(report_paths),
        "artifacts": {task.task_name: task.output_uri for task in tasks if task.output_uri},
    }


def assets(registry: ProviderRegistry, limit: int = 100) -> dict[str, object]:
    """Return compatibility assets."""
    return list_assets(registry.settings.database, limit).to_dict()


def signals(registry: ProviderRegistry, limit: int = 100) -> dict[str, object]:
    """Return compatibility signals."""
    return list_signals(registry.settings.database, limit).to_dict()


def backtest(registry: ProviderRegistry, run_id: int) -> dict[str, object]:
    """Return one compatibility backtest run."""
    return get_backtest(registry.settings.database, run_id).to_dict()


def risk(registry: ProviderRegistry, run_id: int) -> dict[str, object]:
    """Return one compatibility risk run."""
    return get_risk(registry.settings.database, run_id).to_dict()


def models(registry: ProviderRegistry) -> dict[str, object]:
    """Return registered model factories and provider-backed artifacts."""
    model_registry = build_default_model_registry()
    try:
        artifacts = registry.get_model_registry().list_models()
        warning = ""
    except Exception as exc:
        artifacts = []
        warning = str(exc)
    payload: dict[str, object] = {
        "factories": list(model_registry.names()),
        "artifacts": artifacts,
    }
    if warning:
        payload["warning"] = warning
    return payload


def storage_presign(
    registry: ProviderRegistry,
    path: str,
    expires_seconds: int = 3600,
) -> dict[str, object]:
    """Return a local or cloud storage read URI through the storage provider."""
    if expires_seconds > registry.settings.security.max_presigned_url_expiry_seconds:
        raise ValueError("presigned URL expiry exceeds configured maximum")
    safe_path = validate_storage_key(path, registry.settings.security.allowed_storage_prefixes)
    return {
        "path": safe_path,
        "expires_seconds": expires_seconds,
        "url": registry.get_storage().presign_read(safe_path, expires_seconds),
    }


def _submit_task_run(
    registry: ProviderRegistry,
    name: str,
    task_name: str,
    config_key: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    task_payload = dict(payload)
    config = {
        "name": name,
        "pipeline": {"name": name, "tasks": [task_name]},
        config_key: task_payload,
    }
    safe_config = validate_uploaded_config(config, registry.settings)
    return _submit_orchestrated_run(registry, safe_config, sync=_sync_requested(payload))


def _submit_orchestrated_run(
    registry: ProviderRegistry,
    config: Mapping[str, object],
    *,
    sync: bool,
) -> dict[str, object]:
    runner = LocalPipelineRunner(registry)
    if sync and registry.settings.compute.provider == "local":
        result = runner.run(config)
        payload = result.to_dict()
        return {"run_id": result.run.id, "status": result.run.status, "queued": False, **payload}
    run = runner.state.create_run(_pipeline_name(config), dict(config), status="QUEUED")  # type: ignore[union-attr]
    message_id = registry.get_queue().publish("pipeline.run", {"run_id": run.id, "config": dict(config)})
    return {"run_id": run.id, "status": "PLANNED", "queued": True, "queue_message_id": message_id, "run": run.to_dict()}


def _pipeline_payload(payload: Mapping[str, object]) -> dict[str, object]:
    config = payload.get("config")
    return dict(config) if isinstance(config, Mapping) else dict(payload)


def _pipeline_name(config: Mapping[str, object]) -> str:
    pipeline = config.get("pipeline") if isinstance(config.get("pipeline"), Mapping) else config
    if isinstance(pipeline, Mapping):
        return str(pipeline.get("name") or config.get("name") or "api_pipeline")
    return str(config.get("name") or "api_pipeline")


def _compute_run_config(name: str, payload: Mapping[str, object]) -> dict[str, object]:
    return {"name": name, "pipeline": {"name": name, "tasks": []}, "compute": dict(payload)}


def _feature_build_result(payload: Mapping[str, object]) -> dict[str, object]:
    result = build_feature_store(payload)
    return {
        "output_path": str(result.output_path),
        "row_count": result.row_count,
        "version": result.version,
        "groups": list(result.groups),
        "metadata_rows": result.metadata_rows,
    }


def _train_model_result(
    registry: ProviderRegistry,
    payload: Mapping[str, object],
) -> dict[str, object]:
    model_name = str(payload.get("model_name") or payload.get("name") or "naive_return")
    model_config = dict(_mapping(payload.get("config")))
    dataset = _rows(payload.get("dataset"))
    fit_config = dict(_mapping(payload.get("fit_config")))
    model = build_default_model_registry().create(model_name, model_config)
    model.fit(dataset, fit_config)
    output_path = str(payload.get("output_path") or "")
    artifact_uri = ""
    if output_path:
        artifact_path = model.save(output_path)
        artifact_uri = registry.get_model_registry().save_model(
            model.metadata().get("model_name", model_name).__str__(),
            str(model.metadata().get("model_version", "v1")),
            artifact_path,
            model.metadata(),
        )["artifact_uri"].__str__()
    return {"model": model.metadata(), "artifact_uri": artifact_uri}


def _predict_model_result(payload: Mapping[str, object]) -> dict[str, object]:
    model_name = str(payload.get("model_name") or payload.get("name") or "naive_return")
    model_config = dict(_mapping(payload.get("config")))
    train_dataset = _rows(payload.get("train_dataset"))
    dataset = _rows(payload.get("dataset"))
    fit_config = dict(_mapping(payload.get("fit_config")))
    horizon = payload.get("horizon", "1d")
    model = build_default_model_registry().create(model_name, model_config)
    if train_dataset:
        model.fit(train_dataset, fit_config)
    output_path = payload.get("output_path")
    database_url = payload.get("database_url")
    result = run_batch_prediction(
        model,
        dataset,
        horizon,
        output_path=Path(str(output_path)) if output_path else None,
        database_url=str(database_url) if database_url else None,
        feature_set_version=str(payload.get("feature_set_version") or ""),
    )
    return {
        "predictions": prediction_rows(result.predictions),
        "explanations": result.explanations,
        "parquet_path": str(result.parquet_path) if result.parquet_path else "",
        "signal_count": result.signal_count,
    }


def _safe_check(check: object) -> dict[str, object]:
    try:
        return {"ok": bool(check())}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _sync_requested(payload: Mapping[str, object]) -> bool:
    return str(payload.get("sync", "false")).lower() in {"1", "true", "yes", "on"}


def _bool(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: object) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]
