"""Scheduler adapters for orchestrated pipeline runs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.orchestration.local_runner import LocalPipelineRunner, PipelineRunResult
from src.providers.base import MissingProviderDependencyError


@dataclass(frozen=True, slots=True)
class PipelineScheduler:
    """Thin scheduler adapter around the local pipeline runner."""

    runner: LocalPipelineRunner
    provider: str = "local"

    def run(self, config: Mapping[str, object]) -> PipelineRunResult:
        """Execute or delegate a pipeline run."""
        if self.provider == "local":
            return self.runner.run(config)
        if self.provider == "apscheduler":
            return self._run_apscheduler(config)
        if self.provider in {"prefect", "dagster"}:
            raise MissingProviderDependencyError(
                f"{self.provider} orchestration adapter is optional and not configured"
            )
        raise ValueError(f"Unknown orchestration provider {self.provider!r}")

    def _run_apscheduler(self, config: Mapping[str, object]) -> PipelineRunResult:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError as exc:
            raise MissingProviderDependencyError(
                "apscheduler is required when ORCHESTRATOR=apscheduler"
            ) from exc
        scheduler = BackgroundScheduler()
        scheduler.start(paused=True)
        try:
            return self.runner.run(config)
        finally:
            scheduler.shutdown(wait=False)


def build_pipeline_scheduler(runner: LocalPipelineRunner, provider: str = "local") -> PipelineScheduler:
    """Build a scheduler adapter."""
    return PipelineScheduler(runner, provider)
