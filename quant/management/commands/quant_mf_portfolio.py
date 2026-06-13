"""Run multifractal portfolio allocation from CLI inputs."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant.services.multifractal.cli_support import (
    diagonal_covariance,
    json_text,
    parse_float_series,
    parse_symbols,
)
from quant.services.multifractal.portfolio.multifractal_optimizer import (
    optimize_multifractal_adjusted_portfolio,
)


class Command(BaseCommand):
    """Run a research-only multifractal allocation."""

    help = "Run Quant multifractal portfolio allocation from local inputs."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register portfolio command options."""
        parser.add_argument("--symbols", required=True)
        parser.add_argument("--variances", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Compute and print weights."""
        symbols = parse_symbols(str(options["symbols"]))
        variances = parse_float_series(str(options["variances"]))
        covariance = diagonal_covariance(variances)
        result = optimize_multifractal_adjusted_portfolio(symbols, covariance, {})
        self.stdout.write(json_text(result.to_json_dict()))
