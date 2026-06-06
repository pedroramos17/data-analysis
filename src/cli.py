"""Command-line entrypoint for provider-neutral project utilities."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.api.handlers import backtest_run, models_predict, models_train, risk_run
from src.cli_commands import src_cli_command
from src.config.settings import load_runtime_settings
from src.cost import estimate_costs, plan_costs
from src.models.registry import build_default_model_registry
from src.observability.efficiency import build_efficiency_report, write_efficiency_report
from src.orchestration import LocalPipelineRunner, build_pipeline_scheduler
from src.orchestration.state import PipelineStateStore
from src.pipeline.evaluation import run_backtest_from_config, run_evaluation
from src.pipeline.features import run_feature_pipeline
from src.pipeline.ingestion import run_ingestion, validate_ingestion_path
from src.pipeline.preprocessing import run_preprocessing
from src.pipeline.training import run_training, submit_runpod_training_job
from src.pipeline.windows import build_dataset, inspect_dataset
from src.providers.provenance import build_provider_provenance
from src.providers.registry import ProviderRegistry, build_provider_registry
from src.providers.storage.local import LocalStorageProvider
from src.security.audit_log import audit_gpu_cancel, audit_gpu_submit
from src.security.secret_redaction import env_secret_values, redact_secrets
from src.security.validation import validate_config_file_path
from src.warehouse.materialize import build_panel_from_config
from src.workflows import run_mvp_demo


def main(argv: list[str] | None = None) -> int:
    """Run the `python3 -m src.cli` command."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args, parser)
    except Exception as exc:
        print(f"error: {_friendly_error(exc)}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    registry = _registry()
    command = args.command
    if command == "config" and args.config_command == "show":
        return _print_json(build_provider_provenance(registry.settings))
    if command == "db" and args.db_command == "migrate":
        return _print_json(_db_migrate(registry))
    if command == "ingest" and args.ingest_command == "run":
        return _print_json(run_ingestion(_read_config(Path(args.config)), registry).to_dict())
    if command == "ingest" and args.ingest_command == "validate":
        return _print_json(validate_ingestion_path(args.path))
    if command == "preprocess" and args.preprocess_command == "run":
        return _print_json(run_preprocessing(_read_config(Path(args.config)), registry).to_dict())
    if command == "features" and args.features_command in {"build", "build-store"}:
        return _features_build(registry, args)
    if command == "warehouse" and args.warehouse_command == "build-panel":
        return _warehouse_build_panel(args)
    if command == "model" and args.model_command == "train":
        return _print_json(models_train(registry, _sync_config(Path(args.config))))
    if command == "model" and args.model_command == "predict":
        return _print_json(models_predict(registry, _sync_config(Path(args.config))))
    if command == "backtest" and args.backtest_command == "run":
        return _backtest_run(registry, args)
    if command == "evaluate" and args.evaluate_command == "run":
        return _print_json(run_evaluation(_read_config(Path(args.config)), registry).to_dict())
    if command == "risk" and args.risk_command == "run":
        return _print_json(risk_run(registry, _read_config(Path(args.config))))
    if command == "mvp-demo":
        return _mvp_demo(args)
    if command == "storage" and args.storage_command == "sync":
        return _print_json(_storage_sync(registry, args.source, args.target, args.prefix))
    if command == "gpu-job-dry-run":
        return _gpu_job_dry_run(registry, args)
    if command == "compute" and args.compute_command == "runpod":
        return _compute_runpod(args)
    if command == "cost":
        return _cost_command(registry, args)
    if command == "train" and args.train_command == "run":
        return _print_json(run_training(_read_config(Path(args.config)), registry).to_dict())
    if command == "train" and args.train_command == "run-windowed":
        return _print_json(run_training(_read_config(Path(args.config)), registry).to_dict())
    if command == "train" and args.train_command == "runpod":
        return _train_runpod(args)
    if command == "windows" and args.windows_command == "build":
        return _windows_build(registry, args)
    if command == "windows" and args.windows_command == "inspect":
        return _windows_inspect(args)
    if command == "pipeline":
        return _pipeline_command(registry, args)
    if command == "efficiency":
        return _efficiency_command(registry, args)
    if command == "smoke-test":
        return _print_json(_smoke_test(registry))
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=src_cli_command())
    subcommands = parser.add_subparsers(dest="command")

    config = subcommands.add_parser("config")
    config_subcommands = config.add_subparsers(dest="config_command")
    config_subcommands.add_parser("show")

    db = subcommands.add_parser("db")
    db_subcommands = db.add_subparsers(dest="db_command")
    db_subcommands.add_parser("migrate")

    ingest = subcommands.add_parser("ingest")
    ingest_subcommands = ingest.add_subparsers(dest="ingest_command")
    ingest_run_parser = ingest_subcommands.add_parser("run")
    ingest_run_parser.add_argument("--config", required=True)
    ingest_validate_parser = ingest_subcommands.add_parser("validate")
    ingest_validate_parser.add_argument("--path", required=True)

    preprocess = subcommands.add_parser("preprocess")
    preprocess_subcommands = preprocess.add_subparsers(dest="preprocess_command")
    preprocess_run = preprocess_subcommands.add_parser("run")
    preprocess_run.add_argument("--config", required=True)

    features = subcommands.add_parser("features")
    features_subcommands = features.add_subparsers(dest="features_command")
    features_build = features_subcommands.add_parser("build")
    features_build.add_argument("--config", required=True)
    build_store = features_subcommands.add_parser("build-store")
    build_store.add_argument("--config", required=True)

    warehouse = subcommands.add_parser("warehouse")
    warehouse_subcommands = warehouse.add_subparsers(dest="warehouse_command")
    build_panel = warehouse_subcommands.add_parser("build-panel")
    build_panel.add_argument("--config", required=True)

    model = subcommands.add_parser("model")
    model_subcommands = model.add_subparsers(dest="model_command")
    model_train = model_subcommands.add_parser("train")
    model_train.add_argument("--config", required=True)
    model_predict = model_subcommands.add_parser("predict")
    model_predict.add_argument("--config", required=True)

    backtest = subcommands.add_parser("backtest")
    backtest_subcommands = backtest.add_subparsers(dest="backtest_command")
    backtest_run_parser = backtest_subcommands.add_parser("run")
    backtest_run_parser.add_argument("--config", required=True)

    evaluate = subcommands.add_parser("evaluate")
    evaluate_subcommands = evaluate.add_subparsers(dest="evaluate_command")
    evaluate_run_parser = evaluate_subcommands.add_parser("run")
    evaluate_run_parser.add_argument("--config", required=True)

    risk = subcommands.add_parser("risk")
    risk_subcommands = risk.add_subparsers(dest="risk_command")
    risk_run_parser = risk_subcommands.add_parser("run")
    risk_run_parser.add_argument("--config", required=True)

    mvp_demo = subcommands.add_parser("mvp-demo")
    mvp_demo.add_argument("--config", required=True)

    storage = subcommands.add_parser("storage")
    storage_subcommands = storage.add_subparsers(dest="storage_command")
    storage_sync = storage_subcommands.add_parser("sync")
    storage_sync.add_argument("--from", dest="source", choices=("local", "object"), required=True)
    storage_sync.add_argument("--to", dest="target", choices=("local", "object"), required=True)
    storage_sync.add_argument("--prefix", default="")

    gpu_dry_run = subcommands.add_parser("gpu-job-dry-run")
    gpu_dry_run.add_argument("--task", default="train_mamba")
    gpu_dry_run.add_argument("--model", default="fin_mamba")
    gpu_dry_run.add_argument("--dataset-uri", default="data/lake/gold/training_dataset.parquet")
    gpu_dry_run.add_argument("--output", default="exports/gpu_jobs/runpod_dry_run.json")
    gpu_dry_run.add_argument(
        "--command",
        dest="job_command",
        default=src_cli_command("model", "train", "--config", "configs/model_fin_mamba_small.yaml"),
    )

    compute = subcommands.add_parser("compute")
    compute_subcommands = compute.add_subparsers(dest="compute_command")
    runpod = compute_subcommands.add_parser("runpod")
    runpod_subcommands = runpod.add_subparsers(dest="runpod_command")
    runpod_dry_run = runpod_subcommands.add_parser("dry-run")
    runpod_dry_run.add_argument("--config", required=True)
    runpod_dry_run.add_argument("--output", default="")
    runpod_submit = runpod_subcommands.add_parser("submit")
    runpod_submit.add_argument("--config", required=True)
    runpod_submit.add_argument("--confirm-cost", action="store_true")
    runpod_status = runpod_subcommands.add_parser("status")
    runpod_status.add_argument("--job-id", required=True)
    runpod_logs = runpod_subcommands.add_parser("logs")
    runpod_logs.add_argument("--job-id", required=True)
    runpod_cancel = runpod_subcommands.add_parser("cancel")
    runpod_cancel.add_argument("--job-id", required=True)
    runpod_subcommands.add_parser("cleanup-idle")

    cost = subcommands.add_parser("cost")
    cost_subcommands = cost.add_subparsers(dest="cost_command")
    cost_estimate = cost_subcommands.add_parser("estimate")
    cost_estimate.add_argument("--config", required=True)
    cost_plan = cost_subcommands.add_parser("plan")
    cost_plan.add_argument("--config", required=True)
    cost_plan.add_argument("--confirm-cost", action="store_true")

    train = subcommands.add_parser("train")
    train_subcommands = train.add_subparsers(dest="train_command")
    train_run = train_subcommands.add_parser("run")
    train_run.add_argument("--config", required=True)
    train_windowed = train_subcommands.add_parser("run-windowed")
    train_windowed.add_argument("--config", required=True)
    train_runpod = train_subcommands.add_parser("runpod")
    train_runpod.add_argument("--config", required=True)
    train_runpod.add_argument("--confirm-cost", action="store_true")

    windows = subcommands.add_parser("windows")
    windows_subcommands = windows.add_subparsers(dest="windows_command")
    windows_build = windows_subcommands.add_parser("build")
    windows_build.add_argument("--config", required=True)
    windows_inspect = windows_subcommands.add_parser("inspect")
    windows_inspect.add_argument("--dataset", required=True)
    windows_inspect.add_argument("--window-id", type=int, default=None)

    pipeline = subcommands.add_parser("pipeline")
    pipeline_subcommands = pipeline.add_subparsers(dest="pipeline_command")
    pipeline_run = pipeline_subcommands.add_parser("run")
    pipeline_run.add_argument("--config", required=True)
    pipeline_dry_run = pipeline_subcommands.add_parser("dry-run")
    pipeline_dry_run.add_argument("--config", required=True)
    pipeline_resume = pipeline_subcommands.add_parser("resume")
    pipeline_resume.add_argument("--run-id", required=True, type=int)
    pipeline_status = pipeline_subcommands.add_parser("status")
    pipeline_status.add_argument("--run-id", required=True, type=int)

    efficiency = subcommands.add_parser("efficiency")
    efficiency_subcommands = efficiency.add_subparsers(dest="efficiency_command")
    efficiency_report = efficiency_subcommands.add_parser("report")
    efficiency_report.add_argument("--run-id", required=True, type=int)

    subcommands.add_parser("smoke-test")
    return parser


def _features_build(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    result = run_feature_pipeline(_read_config(Path(args.config)), registry)
    return _print_json(result.to_dict())


def _warehouse_build_panel(args: argparse.Namespace) -> int:
    result = build_panel_from_config(_read_config(Path(args.config)))
    return _print_json(
        {
            "materialized": str(result.output_path),
            "rows": result.row_count,
            "source_view": result.source_view,
        }
    )


def _mvp_demo(args: argparse.Namespace) -> int:
    result = run_mvp_demo(_read_config(Path(args.config)))
    return _print_json(result.to_dict())


def _backtest_run(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    config = _read_config(Path(args.config))
    if config.get("evaluation_backtest") or config.get("predictions_path") or config.get("prediction_path"):
        return _print_json(run_backtest_from_config(config, registry))
    return _print_json(backtest_run(registry, config))


def _db_migrate(registry: ProviderRegistry) -> dict[str, object]:
    provider_result = registry.get_db().run_migrations()
    compatibility = _migrate_compatibility_schema(registry)
    return {"database": provider_result, "compatibility_schema": compatibility}


def _migrate_compatibility_schema(registry: ProviderRegistry) -> dict[str, object]:
    try:
        from src.database.core_schema import build_core_engine, create_core_tables
    except ImportError as exc:
        return {"status": "skipped", "reason": f"sqlalchemy unavailable: {exc}"}
    engine = build_core_engine(registry.settings.database)
    try:
        create_core_tables(engine)
    finally:
        engine.dispose()
    return {"status": "ok", "tables": "core_mvp"}


def _storage_sync(
    registry: ProviderRegistry,
    source: str,
    target: str,
    prefix: str,
) -> dict[str, object]:
    if source == target:
        raise ValueError("Invalid storage sync; expected --from and --to to differ")
    local = LocalStorageProvider(registry.settings.storage.local_root)
    object_store = _object_storage_provider(registry)
    source_provider = local if source == "local" else object_store
    target_provider = local if target == "local" else object_store
    keys = source_provider.list(prefix)
    byte_count = 0
    for key in keys:
        data = source_provider.get_bytes(key)
        target_provider.put_bytes(key, data)
        byte_count += len(data)
    return {"source": source, "target": target, "prefix": prefix, "objects": len(keys), "bytes": byte_count}


def _gpu_job_dry_run(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    submission = registry.get_compute().submit_job(
        {
            "name": "gpu-job-dry-run",
            "task": args.task,
            "command": args.job_command,
            "payload": {
                "task": args.task,
                "model": args.model,
                "dataset_uri": args.dataset_uri,
            },
        }
    )
    manifest = {
        "job_id": submission.job_id,
        "status": submission.status,
        "metadata": submission.metadata,
    }
    safe_manifest = redact_secrets(manifest, env_secret_values())
    output_path = Path(str(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(safe_manifest, sort_keys=True, indent=2), encoding="utf-8")
    return _print_json({"output_path": str(output_path), **safe_manifest})


def _compute_runpod(args: argparse.Namespace) -> int:
    registry = _runpod_registry(force_dry_run=args.runpod_command == "dry-run")
    compute = registry.get_compute()
    if args.runpod_command == "dry-run":
        result = submit_runpod_training_job(
            _read_config(Path(args.config)),
            registry,
            dry_run=True,
        )
        return _print_json(_maybe_write_manifest(result, args.output))
    if args.runpod_command == "submit":
        config = _read_config(Path(args.config))
        cost_plan = _runpod_submit_preflight(config, registry, args.confirm_cost)
        audit_gpu_submit(registry.settings, principal="cli", status="started", metadata={"config": config, "cost_plan": cost_plan.to_dict()})
        result = submit_runpod_training_job(
            config,
            registry,
            confirm_cost=args.confirm_cost,
        )
        result["cost_plan"] = cost_plan.to_dict()
        audit_gpu_submit(registry.settings, principal="cli", status=str(result.get("status", "submitted")), metadata=result)
        return _print_json(result)
    if args.runpod_command == "status":
        submission = compute.get_status(args.job_id)
        return _print_json(
            {"job_id": submission.job_id, "status": submission.status, "metadata": submission.metadata}
        )
    if args.runpod_command == "logs":
        return _print_json({"job_id": args.job_id, "logs": compute.stream_logs(args.job_id)})
    if args.runpod_command == "cancel":
        audit_gpu_cancel(registry.settings, principal="cli", status="started", job_id=args.job_id)
        submission = compute.cancel_job(args.job_id)
        audit_gpu_cancel(registry.settings, principal="cli", status=submission.status, job_id=args.job_id, metadata=submission.metadata)
        return _print_json(
            {"job_id": submission.job_id, "status": submission.status, "metadata": submission.metadata}
        )
    if args.runpod_command == "cleanup-idle":
        return _print_json(compute.terminate_idle())
    raise ValueError("Expected compute runpod subcommand")


def _cost_command(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    config = _read_config(Path(args.config))
    if args.cost_command == "estimate":
        return _print_json(estimate_costs(config, registry.settings).to_dict())
    if args.cost_command == "plan":
        return _print_json(
            plan_costs(
                config,
                registry.settings,
                confirm_cost=args.confirm_cost,
            ).to_dict()
        )
    raise ValueError("Expected cost subcommand")


def _train_runpod(args: argparse.Namespace) -> int:
    registry = _runpod_registry()
    config = _read_config(Path(args.config))
    cost_plan = _runpod_submit_preflight(config, registry, args.confirm_cost)
    audit_gpu_submit(registry.settings, principal="cli", status="started", metadata={"config": config, "cost_plan": cost_plan.to_dict()})
    result = submit_runpod_training_job(config, registry, confirm_cost=args.confirm_cost)
    result["cost_plan"] = cost_plan.to_dict()
    audit_gpu_submit(registry.settings, principal="cli", status=str(result.get("status", "submitted")), metadata=result)
    return _print_json(result)


def _runpod_submit_preflight(
    config: Mapping[str, object],
    registry: ProviderRegistry,
    confirm_cost: bool,
) -> object:
    cost_plan = plan_costs(config, registry.settings, confirm_cost=confirm_cost)
    if not registry.settings.runpod.dry_run:
        _print_runpod_cost_preflight(cost_plan.to_dict())
        if cost_plan.selected_option.provider != "runpod":
            raise ValueError(
                f"Cost planner selected {cost_plan.selected_option.name}; refusing paid RunPod submit"
            )
        if not cost_plan.allowed:
            raise ValueError(
                "RunPod cost preflight failed: " + "; ".join(cost_plan.budget.violations)
            )
    return cost_plan


def _print_runpod_cost_preflight(cost_plan: Mapping[str, object]) -> None:
    print(json.dumps(redact_secrets({"cost_preflight": cost_plan}, env_secret_values()), sort_keys=True, indent=2, default=str), file=sys.stderr)


def _maybe_write_manifest(payload: Mapping[str, object], output: str) -> dict[str, object]:
    safe_payload = redact_secrets(payload, env_secret_values())
    if not output:
        return dict(safe_payload)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(safe_payload, sort_keys=True, indent=2, default=str), encoding="utf-8")
    return {"output_path": str(output_path), **dict(safe_payload)}


def _object_storage_provider(registry: ProviderRegistry) -> object:
    if registry.settings.storage.uses_remote_object_storage():
        return registry.get_storage()
    raise ValueError(
        "storage sync with object storage requires STORAGE_PROVIDER=s3|r2|b2|minio, "
        "OBJECT_STORAGE_BUCKET, and provider credentials"
    )


def _smoke_test(registry: ProviderRegistry) -> dict[str, object]:
    return {
        "runtime": build_provider_provenance(registry.settings),
        "db": _check(lambda: registry.get_db().healthcheck()),
        "queue": _check(lambda: registry.get_queue().healthcheck()),
        "storage": _check(lambda: registry.get_storage().list("") is not None),
        "models": list(build_default_model_registry().names()),
    }


def _check(callback: object) -> dict[str, object]:
    try:
        return {"ok": bool(callback())}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _sync_config(path: Path) -> dict[str, Any]:
    config = _read_config(path)
    config.setdefault("sync", True)
    return config


def _registry() -> ProviderRegistry:
    return build_provider_registry(load_runtime_settings())


def _runpod_registry(*, force_dry_run: bool = False) -> ProviderRegistry:
    env = dict(os.environ)
    env["COMPUTE_PROVIDER"] = "runpod"
    if force_dry_run:
        env["RUNPOD_DRY_RUN"] = "true"
    return build_provider_registry(load_runtime_settings(env=env))


def _read_config(path: Path) -> dict[str, Any]:
    safe_path = validate_config_file_path(path, load_runtime_settings().security.allowed_config_roots)
    if not safe_path.exists():
        raise FileNotFoundError(f"Config file not found: {safe_path}")
    if safe_path.suffix.lower() == ".json":
        return json.loads(safe_path.read_text(encoding="utf-8"))
    try:
        import yaml
    except ImportError:
        return _read_simple_yaml(safe_path)
    loaded = yaml.safe_load(safe_path.read_text(encoding="utf-8")) or {}
    if isinstance(loaded, dict):
        return dict(loaded)
    raise ValueError(f"Invalid config {path}; expected mapping at document root")


def _read_simple_yaml(path: Path) -> dict[str, Any]:
    """Parse the simple key/list YAML shape used by dependency-light configs."""
    lines = _yaml_lines(path)
    parsed, _ = _parse_yaml_mapping(lines, 0, 0)
    return parsed


def _yaml_lines(path: Path) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))
    return lines


def _parse_yaml_mapping(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, stripped = lines[index]
        if line_indent < indent:
            break
        if line_indent > indent or stripped.startswith("-") or ":" not in stripped:
            break
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        index += 1
        if value:
            result[key] = _yaml_scalar(value)
            continue
        if index >= len(lines) or lines[index][0] <= line_indent:
            result[key] = {}
            continue
        if lines[index][1].startswith("-"):
            result[key], index = _parse_yaml_list(lines, index, lines[index][0])
        else:
            result[key], index = _parse_yaml_mapping(lines, index, lines[index][0])
    return result, index


def _parse_yaml_list(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        line_indent, stripped = lines[index]
        if line_indent < indent or not stripped.startswith("-"):
            break
        if line_indent > indent:
            break
        value = stripped[1:].strip()
        result.append(_yaml_scalar(value))
        index += 1
    return result, index


def _yaml_scalar(value: str) -> object:
    """Parse a minimal YAML scalar."""
    text = value.strip().strip('"').strip("'")
    lowered = text.lower()
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _print_json(payload: Mapping[str, object]) -> int:
    print(json.dumps(redact_secrets(payload, env_secret_values()), sort_keys=True, indent=2, default=str))
    return 0


def _windows_build(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    config = _read_config(Path(args.config))
    result = build_dataset(config, registry)
    return _print_json(result.to_dict())


def _windows_inspect(args: argparse.Namespace) -> int:
    lake_root = Path(load_runtime_settings().storage.local_root)
    output_root = lake_root / "datasets"
    result = inspect_dataset(args.dataset, output_root, args.window_id)
    return _print_json(result)


def _pipeline_command(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    runner = LocalPipelineRunner(registry)
    if args.pipeline_command == "dry-run":
        return _print_json(runner.dry_run(_read_config(Path(args.config))))
    if args.pipeline_command == "run":
        scheduler = build_pipeline_scheduler(runner, registry.settings.pipeline.orchestrator)
        return _print_json(scheduler.run(_read_config(Path(args.config))).to_dict())
    if args.pipeline_command == "resume":
        return _print_json(runner.resume(args.run_id).to_dict())
    if args.pipeline_command == "status":
        return _print_json(runner.status(args.run_id))
    raise ValueError("Expected pipeline subcommand")


def _efficiency_command(registry: ProviderRegistry, args: argparse.Namespace) -> int:
    if args.efficiency_command == "report":
        return _print_json(_efficiency_report(registry, args.run_id))
    raise ValueError("Expected efficiency subcommand")


def _efficiency_report(registry: ProviderRegistry, run_id: int) -> dict[str, object]:
    state = PipelineStateStore.from_settings(registry.settings)
    run = state.get_run(run_id)
    efficiency = dict(run.efficiency_json)
    report = efficiency.get("report") if isinstance(efficiency.get("report"), Mapping) else None
    paths = efficiency.get("report_paths") if isinstance(efficiency.get("report_paths"), Mapping) else None
    if report is None:
        metrics = [task.metadata_json.get("efficiency", {}) for task in state.list_tasks(run_id) if task.metadata_json.get("efficiency")]
        report = build_efficiency_report(run_id, metrics, _efficiency_config(registry, run.config_json))
        paths = write_efficiency_report(run_id, report, registry.settings.efficiency.report_root)
    return {
        "run_id": run_id,
        "status": run.status,
        "report": report,
        "report_paths": dict(paths or {}),
    }


def _efficiency_config(registry: ProviderRegistry, config: Mapping[str, object]) -> dict[str, object]:
    if isinstance(config.get("efficiency_gates"), Mapping):
        return dict(config)
    efficiency = registry.settings.efficiency
    return {
        **dict(config),
        "efficiency_gates": {
            "max_pipeline_minutes_local": efficiency.max_pipeline_minutes_local,
            "max_peak_memory_mb": efficiency.max_peak_memory_mb,
            "min_rows_per_second": efficiency.min_rows_per_second,
            "max_gpu_job_minutes": efficiency.max_gpu_job_minutes,
            "max_cost_per_run_usd": efficiency.max_cost_per_run_usd,
        },
    }


def _friendly_error(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, FileNotFoundError) and message.startswith("Config file not found"):
        return f"{message}. Check that the --config path exists and is under ALLOWED_CONFIG_ROOTS."
    if "config path" in message or "path traversal" in message:
        return f"{message}. Use a .json/.yaml file under configs/ or configure ALLOWED_CONFIG_ROOTS."
    if "Unknown pipeline run id" in message:
        return f"{message}. Run `python3 -m src.cli pipeline run --config configs/pipeline_mvp.yaml` first or check the run id."
    if "OBJECT_STORAGE" in message or "boto3" in message:
        return (
            f"{message}. For cloud/object storage, set STORAGE_PROVIDER, "
            "OBJECT_STORAGE_BUCKET, OBJECT_STORAGE_ACCESS_KEY_ID, "
            "OBJECT_STORAGE_SECRET_ACCESS_KEY, and optional OBJECT_STORAGE_ENDPOINT_URL."
        )
    if "DATABASE_URL" in message or "psycopg" in message:
        return (
            f"{message}. For Postgres, set DATABASE_URL or POSTGRES_DB, "
            "POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_HOST."
        )
    return message


if __name__ == "__main__":
    raise SystemExit(main())
