"""Run Quant local portfolio optimizers."""

from __future__ import annotations

import json
from datetime import date

from django.core.management.base import BaseCommand, CommandParser

from quant.services.portfolio.optimizers import (
    optimize_portfolio,
    persist_portfolio_run,
)
from quant.services.run_metadata import parse_iso_date_range


class Command(BaseCommand):
    """Persist a Quant portfolio optimization run."""

    help = "Run local Quant portfolio optimization and persist a PortfolioRun."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register portfolio optimizer options."""
        parser.add_argument("--name", default="quant-portfolio-run")
        parser.add_argument("--symbols", required=True)
        parser.add_argument("--optimizer", default="equal_weight")
        parser.add_argument("--covariance-json", default="[]")
        parser.add_argument("--expected-returns-json", default="{}")
        parser.add_argument("--volatilities-json", default="{}")
        parser.add_argument("--current-weights-json", default="{}")
        parser.add_argument("--output-dir", default="data/quant_portfolios")
        parser.add_argument("--data-start", required=True)
        parser.add_argument("--data-end", required=True)
        parser.add_argument("--split-start", required=True)
        parser.add_argument("--split-end", required=True)
        parser.add_argument("--random-seed", type=int, default=0)

    def handle(self, *args: object, **options: object) -> None:
        """Run optimizer and write the shared PortfolioRun id."""
        current_weights = _float_mapping(options["current_weights_json"], "current")
        result = optimize_portfolio(
            symbols=_symbols(options["symbols"]),
            optimizer_name=str(options["optimizer"]),
            covariance=_matrix(options["covariance_json"]),
            expected_returns=_float_mapping(
                options["expected_returns_json"],
                "returns",
            ),
            volatilities=_float_mapping(options["volatilities_json"], "volatility"),
        )
        run = persist_portfolio_run(
            name=str(options["name"]),
            result=result,
            output_dir=str(options["output_dir"]),
            data_range=_date_range(options, "data"),
            split_range=_date_range(options, "split"),
            current_weights=current_weights,
            random_seed=int(options["random_seed"]),
        )
        self.stdout.write(f"portfolio_run_id={run.pk}")


def _symbols(raw_value: object) -> list[str]:
    symbols = [symbol.strip() for symbol in str(raw_value).split(",") if symbol.strip()]
    if symbols:
        return symbols
    raise ValueError(f"Invalid symbols {raw_value!r}; expected comma-separated symbols")


def _matrix(raw_value: object) -> list[list[float]]:
    parsed = json.loads(str(raw_value))
    if not isinstance(parsed, list):
        raise ValueError(f"Invalid covariance {parsed!r}; expected JSON matrix")
    return [[float(value) for value in row] for row in parsed]


def _float_mapping(raw_value: object, label: str) -> dict[str, float]:
    parsed = json.loads(str(raw_value))
    if isinstance(parsed, dict):
        return {str(symbol): float(value) for symbol, value in parsed.items()}
    raise ValueError(f"Invalid {label} {parsed!r}; expected JSON object")


def _date_range(options: dict[str, object], prefix: str) -> tuple[date, date]:
    return parse_iso_date_range(
        options[f"{prefix}_start"],
        options[f"{prefix}_end"],
        f"{prefix}_range",
    )
