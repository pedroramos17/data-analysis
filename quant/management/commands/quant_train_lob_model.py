"""Train local Quant LOB baselines."""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandParser

from quant.services.lob.lob_backtest import train_lob_baseline_run
from quant.services.run_metadata import parse_iso_date_range


class Command(BaseCommand):
    """Persist a local LOB model run."""

    help = "Train a local Quant LOB baseline and persist an LOBRun."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register LOB model training options."""
        parser.add_argument("--name", default="quant-lob-run")
        parser.add_argument("--input-path", required=True)
        parser.add_argument("--output-dir", default="data/quant_lob")
        parser.add_argument("--model", default="naive_imbalance")
        parser.add_argument("--horizon", type=int, default=1)
        parser.add_argument("--data-start", required=True)
        parser.add_argument("--data-end", required=True)
        parser.add_argument("--split-start", required=True)
        parser.add_argument("--split-end", required=True)
        parser.add_argument("--random-seed", type=int, default=0)

    def handle(self, *args: object, **options: object) -> None:
        """Train the baseline and print the persisted run id."""
        run = train_lob_baseline_run(
            name=str(options["name"]),
            input_path=str(options["input_path"]),
            output_dir=str(options["output_dir"]),
            data_range=_date_range(options, "data"),
            split_range=_date_range(options, "split"),
            model_name=str(options["model"]),
            horizon=int(options["horizon"]),
            random_seed=int(options["random_seed"]),
        )
        self.stdout.write(f"lob_run_id={run.pk}")


def _date_range(options: dict[str, object], prefix: str) -> tuple[date, date]:
    return parse_iso_date_range(
        options[f"{prefix}_start"],
        options[f"{prefix}_end"],
        f"{prefix}_range",
    )
