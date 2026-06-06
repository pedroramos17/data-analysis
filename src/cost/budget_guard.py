"""Budget guards for cost-plan options before paid execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.config.settings import RuntimeSettings, load_runtime_settings
from src.cost.estimator import CostOption, estimate_costs


@dataclass(frozen=True, slots=True)
class BudgetGuardResult:
    """Result of validating a cost option against runtime budgets."""

    allowed: bool
    reasons: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly guard result."""
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "violations": list(self.violations),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class BudgetGuard:
    """Enforce per-job, hourly, daily, and runtime budgets."""

    settings: RuntimeSettings

    def check_option(
        self,
        option: CostOption,
        *,
        confirm_cost: bool = False,
        current_hourly_spend_usd: float = 0.0,
        spent_today_usd: float = 0.0,
    ) -> BudgetGuardResult:
        """Return whether an option stays inside configured budgets."""
        violations: list[str] = []
        reasons: list[str] = list(option.reasons)
        if not option.eligible:
            violations.append("option is not eligible for this workload")
        if option.provider == "runpod" or option.launches_paid_infrastructure:
            self._check_remote_option(
                option,
                violations,
                confirm_cost=confirm_cost,
                current_hourly_spend_usd=current_hourly_spend_usd,
                spent_today_usd=spent_today_usd,
            )
        if not option.launches_paid_infrastructure:
            reasons.append("does not launch paid infrastructure")
        if not violations:
            reasons.append("budget ok")
        return BudgetGuardResult(
            allowed=not violations,
            reasons=tuple(reasons),
            violations=tuple(violations),
            metadata=self._metadata(option, current_hourly_spend_usd, spent_today_usd),
        )

    def check_config(
        self,
        config: Mapping[str, object],
        *,
        option_name: str | None = None,
        confirm_cost: bool = False,
        current_hourly_spend_usd: float = 0.0,
        spent_today_usd: float = 0.0,
    ) -> BudgetGuardResult:
        """Estimate a config and validate one option or the recommended option."""
        estimate = estimate_costs(config, self.settings)
        option = estimate.option(option_name) if option_name else estimate.cheapest_eligible()
        if option is None:
            return BudgetGuardResult(False, violations=("no cost option available",))
        return self.check_option(
            option,
            confirm_cost=confirm_cost,
            current_hourly_spend_usd=current_hourly_spend_usd,
            spent_today_usd=spent_today_usd,
        )

    def _check_remote_option(
        self,
        option: CostOption,
        violations: list[str],
        *,
        confirm_cost: bool,
        current_hourly_spend_usd: float,
        spent_today_usd: float,
    ) -> None:
        if option.launches_paid_infrastructure and self.settings.cost.require_budget_approval and not confirm_cost:
            violations.append("real paid job requires --confirm-cost")
        if option.hourly_cost_usd > self.settings.runpod.max_hourly_cost_usd:
            violations.append("hourly cost exceeds RUNPOD_MAX_HOURLY_COST")
        if option.hourly_cost_usd > self.settings.cost.max_gpu_hourly_cost_usd:
            violations.append("hourly cost exceeds MAX_GPU_HOURLY_COST_USD")
        if option.estimated_cost_usd > self.settings.cost.max_job_cost_usd:
            violations.append("estimated job cost exceeds CLOUD_MAX_JOB_COST_USD")
        if option.estimated_cost_usd > self.settings.efficiency.max_cost_per_run_usd:
            violations.append("estimated job cost exceeds EFFICIENCY_MAX_COST_PER_RUN_USD")
        if option.dataset_size_gb > self.settings.runpod.max_dataset_size_gb:
            violations.append("dataset size exceeds RUNPOD_MAX_DATASET_SIZE_GB")
        if option.estimated_runtime_seconds > self.settings.runpod.max_job_minutes * 60:
            violations.append("runtime exceeds RUNPOD_MAX_JOB_MINUTES")
        if option.estimated_runtime_seconds > self.settings.efficiency.max_gpu_job_minutes * 60:
            violations.append("runtime exceeds EFFICIENCY_MAX_GPU_JOB_MINUTES")
        if current_hourly_spend_usd + option.hourly_cost_usd > self.settings.autoscaling.max_hourly_budget_usd:
            violations.append("autoscaling hourly budget exceeded")
        if spent_today_usd + option.estimated_cost_usd > self.settings.autoscaling.max_daily_budget_usd:
            violations.append("autoscaling daily budget exceeded")

    def _metadata(
        self,
        option: CostOption,
        current_hourly_spend_usd: float,
        spent_today_usd: float,
    ) -> dict[str, object]:
        return {
            "option": option.name,
            "max_job_cost_usd": self.settings.cost.max_job_cost_usd,
            "max_cost_per_run_usd": self.settings.efficiency.max_cost_per_run_usd,
            "runpod_max_hourly_cost_usd": self.settings.runpod.max_hourly_cost_usd,
            "max_gpu_hourly_cost_usd": self.settings.cost.max_gpu_hourly_cost_usd,
            "autoscaling_max_hourly_budget_usd": self.settings.autoscaling.max_hourly_budget_usd,
            "autoscaling_max_daily_budget_usd": self.settings.autoscaling.max_daily_budget_usd,
            "projected_hourly_spend_usd": round(current_hourly_spend_usd + option.hourly_cost_usd, 4),
            "projected_daily_spend_usd": round(spent_today_usd + option.estimated_cost_usd, 4),
        }


def guard_config(
    config: Mapping[str, object],
    settings: RuntimeSettings | None = None,
    *,
    option_name: str | None = None,
    confirm_cost: bool = False,
) -> BudgetGuardResult:
    """Convenience wrapper for one-off config budget checks."""
    active_settings = settings or load_runtime_settings()
    return BudgetGuard(active_settings).check_config(
        config,
        option_name=option_name,
        confirm_cost=confirm_cost,
    )
