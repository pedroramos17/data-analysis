"""Run the safe Quant full-experiment orchestrator."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser
from django.db.utils import OperationalError

from quant.services.full_experiment import (
    FullExperimentConfig,
    dag_summary,
    run_full_experiment,
)
from sourceflow.config.feature_flags import parse_flag_value


class Command(BaseCommand):
    """Plan or run a safe local Quant experiment DAG."""

    help = "Plan or run the safe local Quant full-experiment DAG."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register full-experiment orchestration options."""
        parser.add_argument("--name", required=True)
        parser.add_argument("--asset-classes", default="")
        parser.add_argument("--symbols", default="")
        parser.add_argument("--timeframes", default="1d")
        parser.add_argument("--horizon", type=int, default=1)
        parser.add_argument("--windows", default="walk_forward")
        parser.add_argument("--regimes", default="")
        parser.add_argument("--graphs", default="")
        parser.add_argument("--risk-models", default="")
        parser.add_argument("--models", default="")
        parser.add_argument("--portfolio-optimizers", default="")
        parser.add_argument("--backtest", default="false")
        parser.add_argument("--data-root", default="data/quant")
        parser.add_argument("--compute-profile", default="local_cpu")
        parser.add_argument("--no-live-trading", action="store_true", default=False)
        parser.add_argument("--dry-run", action="store_true", default=True)
        parser.add_argument("--execute", action="store_false", dest="dry_run")

    def handle(self, *args: object, **options: object) -> None:
        """Persist an Experiment record and print the safe DAG outcome."""
        config = _config_from_options(options)
        self.stdout.write(f"Quant DAG: {dag_summary()}")
        self.stdout.write(f"compute_profile={config.compute_profile}")
        self.stdout.write("live_trading=False")
        try:
            result = run_full_experiment(config)
        except OperationalError as exc:
            if _can_skip_persistence(config, exc):
                self.stdout.write(_persistence_skip_message(exc))
                return
            raise
        for line in result.output_lines:
            self.stdout.write(line)
        self.stdout.write(f"experiment_id={result.experiment.pk}")
        self.stdout.write(f"experiment_status={result.experiment.status}")


def _config_from_options(options: dict[str, object]) -> FullExperimentConfig:
    return FullExperimentConfig(
        name=str(options["name"]),
        asset_classes=_csv_list(options["asset_classes"]),
        symbols=_csv_list(options["symbols"]),
        timeframes=_csv_list(options["timeframes"]) or ["1d"],
        horizon=int(options["horizon"]),
        windows=_csv_list(options["windows"]) or ["walk_forward"],
        regimes=_csv_list(options["regimes"]),
        graphs=_csv_list(options["graphs"]),
        risk_models=_csv_list(options["risk_models"]),
        models=_csv_list(options["models"]),
        portfolio_optimizers=_csv_list(options["portfolio_optimizers"]),
        backtest=parse_flag_value(options["backtest"]),
        dry_run=bool(options["dry_run"]),
        live_trading=False,
        compute_profile=_compute_profile(options["compute_profile"]),
        data_root=str(options["data_root"]),
    )


def _csv_list(raw_value: object) -> list[str]:
    return [value.strip() for value in str(raw_value).split(",") if value.strip()]


def _compute_profile(raw_value: object) -> str:
    value = str(raw_value).strip()
    if value:
        return value
    raise ValueError(
        f"Invalid compute_profile {raw_value!r}; expected non-empty string"
    )


def _can_skip_persistence(config: FullExperimentConfig, exc: OperationalError) -> bool:
    return config.dry_run and "quant_experiment" in str(exc)


def _persistence_skip_message(exc: OperationalError) -> str:
    return (
        f"experiment_persistence=skipped reason={str(exc)!r}; "
        "expected migrated Quant database for Experiment records"
    )
