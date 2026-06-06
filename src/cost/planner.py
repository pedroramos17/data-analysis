"""Cost-minimizing execution plans for local and optional GPU training."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.config.settings import RuntimeSettings, load_runtime_settings
from src.cost.budget_guard import BudgetGuard, BudgetGuardResult
from src.cost.estimator import CostEstimate, CostOption, estimate_costs


@dataclass(frozen=True, slots=True)
class CostPlanStep:
    """One action in a cost-minimizing execution plan."""

    action: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly step."""
        return {
            "action": self.action,
            "description": self.description,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CostPlan:
    """Selected cost option, guard result, and execution steps."""

    selected_option: CostOption
    budget: BudgetGuardResult
    steps: tuple[CostPlanStep, ...]
    estimate: CostEstimate
    blocked_options: dict[str, BudgetGuardResult] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """Return whether the selected option passed budget checks."""
        return self.budget.allowed

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly plan."""
        return {
            "allowed": self.allowed,
            "selected_option": self.selected_option.to_dict(),
            "budget": self.budget.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "estimate": self.estimate.to_dict(),
            "blocked_options": {
                name: result.to_dict() for name, result in self.blocked_options.items()
            },
            "metadata": dict(self.metadata),
        }


def plan_costs(
    config: Mapping[str, object],
    settings: RuntimeSettings | None = None,
    *,
    confirm_cost: bool = False,
    current_hourly_spend_usd: float = 0.0,
    spent_today_usd: float = 0.0,
) -> CostPlan:
    """Choose the cheapest safe execution plan for a config."""
    active_settings = settings or load_runtime_settings()
    estimate = estimate_costs(config, active_settings)
    guard = BudgetGuard(active_settings)
    guard_results = {
        option.name: guard.check_option(
            option,
            confirm_cost=confirm_cost,
            current_hourly_spend_usd=current_hourly_spend_usd,
            spent_today_usd=spent_today_usd,
        )
        for option in estimate.options
    }
    selected = _select_option(estimate, guard_results)
    selected_guard = guard_results[selected.name]
    blocked = {
        name: result
        for name, result in guard_results.items()
        if not result.allowed or name != selected.name and estimate.option(name) and not estimate.option(name).eligible
    }
    return CostPlan(
        selected_option=selected,
        budget=selected_guard,
        steps=_steps(selected, estimate, active_settings),
        estimate=estimate,
        blocked_options=blocked,
        metadata={
            "cost_mode": active_settings.pipeline.cost_mode,
            "dry_run": active_settings.runpod.dry_run,
            "full_training_requested": bool(estimate.workload.get("full_training_requested")),
            "confirm_cost": confirm_cost,
        },
    )


def _select_option(
    estimate: CostEstimate,
    guard_results: Mapping[str, BudgetGuardResult],
) -> CostOption:
    workload = estimate.workload
    smoke = bool(workload.get("smoke_mode"))
    local_cpu = _required_option(estimate, "local_cpu")
    local_smoke = _required_option(estimate, "local_smoke")
    runpod = _required_option(estimate, "runpod_gpu")
    batched = _required_option(estimate, "runpod_batched_gpu")

    if smoke and guard_results[local_smoke.name].allowed:
        return local_smoke
    if workload.get("baseline_model") and guard_results[local_cpu.name].allowed:
        return local_cpu
    if workload.get("is_small_dataset") and not workload.get("force_gpu") and guard_results[local_cpu.name].allowed:
        return local_cpu
    if workload.get("prefers_gpu") and not workload.get("full_training_requested") and guard_results[local_smoke.name].allowed:
        return local_smoke
    if workload.get("gpu_required") or workload.get("prefers_gpu"):
        gpu_options = [option for option in (batched, runpod) if option.eligible and guard_results[option.name].allowed]
        if gpu_options:
            return min(gpu_options, key=lambda option: (option.estimated_cost_usd, option.estimated_runtime_seconds))
    allowed = [option for option in estimate.options if option.eligible and guard_results[option.name].allowed]
    if allowed:
        return min(allowed, key=lambda option: (option.estimated_cost_usd, option.estimated_runtime_seconds))
    eligible = [option for option in estimate.options if option.eligible]
    if eligible:
        return min(eligible, key=lambda option: (option.estimated_cost_usd, option.estimated_runtime_seconds))
    return min(estimate.options, key=lambda option: (option.estimated_cost_usd, option.estimated_runtime_seconds))


def _steps(
    selected: CostOption,
    estimate: CostEstimate,
    settings: RuntimeSettings,
) -> tuple[CostPlanStep, ...]:
    workload = estimate.workload
    steps: list[CostPlanStep] = []
    if selected.name == "local_cpu":
        steps.append(
            CostPlanStep(
                "run_local_cpu",
                "Run the workload locally on CPU and avoid paid infrastructure.",
                {"model_name": workload["model_name"]},
            )
        )
    elif selected.name == "local_smoke":
        steps.append(
            CostPlanStep(
                "run_local_smoke",
                "Run a downsampled smoke pass before any full training spend.",
                {
                    "sample_fraction": workload["sample_fraction"],
                    "window_count": selected.window_count,
                },
            )
        )
    elif selected.name == "runpod_batched_gpu":
        steps.append(
            CostPlanStep(
                "submit_runpod_batched_gpu",
                "Batch training windows into one bounded RunPod job.",
                {"window_count": selected.window_count, "estimated_cost_usd": round(selected.estimated_cost_usd, 4)},
            )
        )
    elif selected.name == "runpod_gpu":
        steps.append(
            CostPlanStep(
                "submit_runpod_gpu",
                "Submit one bounded RunPod GPU training job.",
                {"estimated_cost_usd": round(selected.estimated_cost_usd, 4)},
            )
        )

    if workload.get("selected_window_count"):
        steps.append(
            CostPlanStep(
                "select_training_windows",
                "Train only the selected windows instead of the full window set.",
                {"selected_window_count": workload["selected_window_count"]},
            )
        )
    if workload.get("reuse_cached_features"):
        steps.append(CostPlanStep("reuse_cached_features", "Reuse cached features before recomputing them."))
    if workload.get("reuse_pretrained_model"):
        steps.append(CostPlanStep("reuse_pretrained_model", "Warm-start from the configured pretrained model."))
    if workload.get("docker_image_cached"):
        steps.append(CostPlanStep("reuse_docker_image_cache", "Prefer the existing GPU image cache."))
    if selected.provider == "runpod" and workload.get("prefer_spot"):
        steps.append(CostPlanStep("prefer_spot_capacity", "Prefer interruptible RunPod capacity when available."))
    if selected.provider == "runpod" and settings.runpod.dry_run:
        steps.append(CostPlanStep("dry_run_only", "Current settings produce a RunPod manifest only; no pod launches."))
    return tuple(steps)


def _required_option(estimate: CostEstimate, name: str) -> CostOption:
    option = estimate.option(name)
    if option is None:
        raise ValueError(f"Missing cost option {name}")
    return option
