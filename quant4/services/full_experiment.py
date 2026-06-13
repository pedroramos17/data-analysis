"""Safe DAG orchestrator for Quant4 full research experiments."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from quant4.services.registry import stable_config_hash
from src.config.settings import load_runtime_settings
from src.providers.provenance import build_provider_provenance

DAG_STEPS = [
    "Data",
    "Windows",
    "Features",
    "Regimes",
    "Risk",
    "Graphs",
    "Models",
    "Portfolio",
    "Backtest",
    "Explainability",
]

OPTIONAL_DEPENDENCIES: dict[str, dict[str, tuple[str, ...]]] = {
    "Regimes": {"rqa": ("pyrqa",)},
    "Graphs": {
        "pmfg": ("pmfg",),
        "leadlag_signature": ("iisignature",),
        "imf_coherence": ("PyEMD",),
        "dynamic_sparse": ("torch_geometric",),
    },
    "Models": {"tcn": ("torch",), "gcn_gru": ("torch", "torch_geometric")},
    "Portfolio": {"hrp": ("scipy",), "cvar": ("cvxpy",)},
}


@dataclass(frozen=True, slots=True)
class FullExperimentConfig:
    """Configuration for a safe Quant4 experiment DAG.

    Example:
        `FullExperimentConfig(name="macro", symbols=["SPY"], dry_run=True)`
    """

    name: str
    asset_classes: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=lambda: ["1d"])
    horizon: int = 1
    windows: list[str] = field(default_factory=lambda: ["walk_forward"])
    regimes: list[str] = field(default_factory=list)
    graphs: list[str] = field(default_factory=list)
    risk_models: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    portfolio_optimizers: list[str] = field(default_factory=list)
    backtest: bool = False
    dry_run: bool = True
    live_trading: bool = False
    compute_profile: str = "local_cpu"
    data_root: str = "data/quant4"
    provider_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StepExecutionResult:
    """Serializable outcome for one DAG step.

    Example:
        `StepExecutionResult("COMPLETED", artifact_paths=["data.csv"])`
    """

    status: str
    reason: str = ""
    artifact_paths: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FullExperimentResult:
    """Persisted experiment plus user-facing run lines.

    Example:
        `run_full_experiment(config).output_lines`
    """

    experiment: object
    steps: list[dict[str, object]]
    output_lines: list[str]


DependencyChecker = Callable[[str], bool]
StepRunner = Callable[[FullExperimentConfig], StepExecutionResult]


def run_full_experiment(
    config: FullExperimentConfig,
    dependency_checker: DependencyChecker | None = None,
    step_runners: Mapping[str, StepRunner] | None = None,
) -> FullExperimentResult:
    """Run or dry-run the Quant4 DAG without live trading.

    Example:
        `run_full_experiment(FullExperimentConfig(name="macro"))`
    """
    _enforce_no_live_trading(config)
    checker = dependency_checker or _dependency_available
    experiment = _upsert_experiment(config, "DRY_RUN" if config.dry_run else "RUNNING")
    step_records = _execute_steps(config, checker, step_runners or {})
    final_status = _final_status(config, step_records)
    _save_experiment_result(experiment, config, step_records, final_status)
    return FullExperimentResult(experiment, step_records, _output_lines(step_records))


def dag_summary() -> str:
    """Return the fixed Quant4 full-experiment DAG.

    Example:
        `dag_summary()`
    """
    return " -> ".join(DAG_STEPS)


def _execute_steps(
    config: FullExperimentConfig,
    dependency_checker: DependencyChecker,
    step_runners: Mapping[str, StepRunner],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for step_name in DAG_STEPS:
        record = _step_record(config, dependency_checker, step_runners, step_name)
        records.append(record)
        if record["status"] == "FAILED":
            break
    return records


def _step_record(
    config: FullExperimentConfig,
    dependency_checker: DependencyChecker,
    step_runners: Mapping[str, StepRunner],
    step_name: str,
) -> dict[str, object]:
    optional_reason = _optional_skip_reason(config, dependency_checker, step_name)
    if optional_reason:
        result = StepExecutionResult("SKIPPED", optional_reason)
        return _serialize_step(step_name, result)
    if config.dry_run:
        return _dry_run_record(step_name)
    return _run_step_record(config, step_runners, step_name)


def _dry_run_record(step_name: str) -> dict[str, object]:
    return _serialize_step(step_name, StepExecutionResult("DRY_RUN", "planned only"))


def _run_step_record(
    config: FullExperimentConfig,
    step_runners: Mapping[str, StepRunner],
    step_name: str,
) -> dict[str, object]:
    try:
        result = _runner_for_step(step_runners, step_name)(config)
    except Exception as exc:
        return _failed_step(step_name, exc)
    return _serialize_step(step_name, result)


def _runner_for_step(
    step_runners: Mapping[str, StepRunner],
    step_name: str,
) -> StepRunner:
    return step_runners.get(step_name, _default_runner(step_name))


def _default_runner(step_name: str) -> StepRunner:
    if step_name == "Data":
        return _run_data_step
    return _skip_without_upstream_artifacts


def _run_data_step(config: FullExperimentConfig) -> StepExecutionResult:
    artifacts = _find_market_data_artifacts(config)
    if artifacts:
        return StepExecutionResult("COMPLETED", artifact_paths=artifacts)
    return StepExecutionResult("SKIPPED", _missing_data_reason(config))


def _skip_without_upstream_artifacts(
    config: FullExperimentConfig,
) -> StepExecutionResult:
    return StepExecutionResult(
        "SKIPPED",
        f"missing upstream artifacts for {config.name!r}; expected completed Data step",
    )


def _find_market_data_artifacts(config: FullExperimentConfig) -> list[str]:
    root = Path(config.data_root)
    if not root.exists():
        return []
    matches = [
        _first_data_match(root, symbol, timeframe)
        for symbol in config.symbols
        for timeframe in config.timeframes
    ]
    return sorted(str(path) for path in matches if path is not None)


def _first_data_match(root: Path, symbol: str, timeframe: str) -> Path | None:
    safe_symbol = _safe_token(symbol)
    safe_timeframe = _safe_token(timeframe)
    candidates = sorted(root.glob(f"**/{safe_symbol}_{safe_timeframe}.*"))
    return candidates[0] if candidates else None


def _optional_skip_reason(
    config: FullExperimentConfig,
    dependency_checker: DependencyChecker,
    step_name: str,
) -> str:
    missing = _missing_optional_components(config, dependency_checker, step_name)
    if not missing:
        return ""
    details = "; ".join(missing)
    return f"optional dependency unavailable: {details}"


def _missing_optional_components(
    config: FullExperimentConfig,
    dependency_checker: DependencyChecker,
    step_name: str,
) -> list[str]:
    requested = _components_for_step(config, step_name)
    requirements = OPTIONAL_DEPENDENCIES.get(step_name, {})
    return [
        _optional_component_message(component, requirements[component])
        for component in requested
        if component in requirements
        and not all(dependency_checker(module) for module in requirements[component])
    ]


def _optional_component_message(component: str, modules: Sequence[str]) -> str:
    return f"{component} requires {', '.join(modules)}"


def _components_for_step(config: FullExperimentConfig, step_name: str) -> list[str]:
    component_map = {
        "Regimes": config.regimes,
        "Graphs": config.graphs,
        "Risk": config.risk_models,
        "Models": config.models,
        "Portfolio": config.portfolio_optimizers,
    }
    return component_map.get(step_name, [])


def _serialize_step(
    step_name: str,
    result: StepExecutionResult,
) -> dict[str, object]:
    record: dict[str, object] = {"name": step_name, "status": result.status}
    if result.reason:
        record["reason"] = result.reason
    if result.artifact_paths:
        record["artifact_paths"] = list(result.artifact_paths)
    if result.metadata:
        record["metadata"] = dict(result.metadata)
    return record


def _failed_step(step_name: str, exc: Exception) -> dict[str, object]:
    return {
        "name": step_name,
        "status": "FAILED",
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }


def _upsert_experiment(
    config: FullExperimentConfig,
    status: str,
) -> object:
    from quant4.models import Experiment

    config_payload = _config_payload(config)
    experiment, _ = Experiment.objects.update_or_create(
        name=config.name,
        defaults={
            "component_name": "quant4_full_experiment",
            "status": status,
            "config_json": config_payload,
            "config_hash": stable_config_hash(config_payload),
            "random_seed": 0,
            "provenance_json": _provenance_payload(config, []),
        },
    )
    return experiment


def _save_experiment_result(
    experiment: object,
    config: FullExperimentConfig,
    step_records: list[dict[str, object]],
    final_status: str,
) -> None:
    experiment.status = final_status
    experiment.provenance_json = _provenance_payload(config, step_records)
    experiment.save(update_fields=["status", "provenance_json", "updated_at"])


def _provenance_payload(
    config: FullExperimentConfig,
    step_records: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "providers": _provider_metadata(config),
        "orchestrator": {
            "dag": list(DAG_STEPS),
            "steps": step_records,
            "dry_run": config.dry_run,
            "live_trading": False,
            "compute_profile": config.compute_profile,
        }
    }


def _provider_metadata(config: FullExperimentConfig) -> dict[str, object]:
    if config.provider_metadata:
        return dict(config.provider_metadata)
    try:
        return build_provider_provenance(load_runtime_settings())
    except Exception as exc:
        return {"error": {"type": type(exc).__name__, "message": str(exc)}}


def _config_payload(config: FullExperimentConfig) -> dict[str, object]:
    return {
        "asset_classes": config.asset_classes,
        "symbols": config.symbols,
        "timeframes": config.timeframes,
        "horizon": config.horizon,
        "windows": config.windows,
        "regimes": config.regimes,
        "graphs": config.graphs,
        "risk_models": config.risk_models,
        "models": config.models,
        "portfolio_optimizers": config.portfolio_optimizers,
        "backtest": config.backtest,
        "dry_run": config.dry_run,
        "live_trading": False,
        "compute_profile": config.compute_profile,
        "data_root": config.data_root,
    }


def _final_status(
    config: FullExperimentConfig,
    step_records: Sequence[Mapping[str, object]],
) -> str:
    statuses = [str(record["status"]) for record in step_records]
    if "FAILED" in statuses:
        return "FAILED"
    if config.dry_run:
        return "DRY_RUN"
    if "SKIPPED" in statuses:
        return "COMPLETED_WITH_SKIPS"
    return "COMPLETED"


def _output_lines(step_records: Sequence[Mapping[str, object]]) -> list[str]:
    return [_output_line(record) for record in step_records]


def _output_line(record: Mapping[str, object]) -> str:
    suffix = _line_suffix(record)
    return f"{record['name']}: {record['status']}{suffix}"


def _line_suffix(record: Mapping[str, object]) -> str:
    if "reason" in record:
        return f" - {record['reason']}"
    if "error" in record:
        return f" - {record['error']}"
    if "artifact_paths" in record:
        return f" - artifacts={record['artifact_paths']}"
    return ""


def _missing_data_reason(config: FullExperimentConfig) -> str:
    return (
        f"missing local data in {config.data_root!r}; "
        "expected files named SYMBOL_TIMEFRAME.*"
    )


def _dependency_available(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def _enforce_no_live_trading(config: FullExperimentConfig) -> None:
    if not config.live_trading:
        return
    raise ValueError("Invalid live_trading=True; expected live_trading disabled")


def _safe_token(value: str) -> str:
    token = "".join(char if char.isalnum() else "_" for char in value.strip())
    return token.strip("_")
