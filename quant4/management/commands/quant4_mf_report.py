"""Generate a compact multifractal research report."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.multifractal.cli_support import default_cli_series
from quant4.services.multifractal.core.mfdfa import run_mfdfa
from quant4.services.multifractal.risk.multifractal_risk import (
    compute_asset_multifractal_risk,
)


class Command(BaseCommand):
    """Render a local Markdown research report."""

    help = "Generate a local Quant4 multifractal Markdown report."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register report command options."""
        parser.add_argument("--symbol", default="LOCAL")

    def handle(self, *args: object, **options: object) -> None:
        """Render a compact report."""
        series = default_cli_series()
        mfdfa = run_mfdfa(series)
        risk = compute_asset_multifractal_risk(series, {"delta_alpha": 0.2})
        self.stdout.write(
            _markdown(str(options["symbol"]), mfdfa.summary, risk.risk_score)
        )


def _markdown(symbol: str, summary: dict[str, object], risk_score: float) -> str:
    return "\n".join(
        [
            "# Multifractal Research Report",
            "",
            f"- Symbol: `{symbol}`",
            f"- H(2): `{summary.get('hurst_h2')}`",
            f"- Risk score: `{risk_score}`",
            "",
            "This report is not a prediction or trading signal.",
        ]
    )
