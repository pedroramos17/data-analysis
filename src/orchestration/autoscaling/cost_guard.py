"""Budget guard for autoscaling decisions."""

from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import AutoscalingSettings


@dataclass(frozen=True, slots=True)
class AutoscalingBudget:
    """Budget inputs for one autoscaling evaluation."""

    current_hourly_spend_usd: float = 0.0
    spent_today_usd: float = 0.0
    candidate_hourly_cost_usd: float = 0.0
    candidate_runtime_seconds: int = 0

    @property
    def candidate_cost_usd(self) -> float:
        """Return estimated total cost for the candidate scale-up."""
        runtime_hours = max(self.candidate_runtime_seconds, 0) / 3600.0
        return runtime_hours * max(self.candidate_hourly_cost_usd, 0.0)


@dataclass(frozen=True, slots=True)
class AutoscalingCostGuard:
    """Enforce hourly and daily autoscaling budgets."""

    settings: AutoscalingSettings

    def can_launch(self, budget: AutoscalingBudget) -> tuple[bool, str]:
        """Return whether launching the candidate stays inside budget."""
        projected_hourly = budget.current_hourly_spend_usd + budget.candidate_hourly_cost_usd
        if projected_hourly > self.settings.max_hourly_budget_usd:
            return False, "autoscaling hourly budget exceeded"
        projected_daily = budget.spent_today_usd + budget.candidate_cost_usd
        if projected_daily > self.settings.max_daily_budget_usd:
            return False, "autoscaling daily budget exceeded"
        return True, "budget ok"

    def remaining_hourly_budget_usd(self, current_hourly_spend_usd: float) -> float:
        """Return remaining hourly budget after current spend."""
        return max(self.settings.max_hourly_budget_usd - current_hourly_spend_usd, 0.0)

    def remaining_daily_budget_usd(self, spent_today_usd: float) -> float:
        """Return remaining daily budget after today's spend."""
        return max(self.settings.max_daily_budget_usd - spent_today_usd, 0.0)
