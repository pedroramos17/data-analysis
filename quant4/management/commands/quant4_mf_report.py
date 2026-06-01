"""Generate a compact multifractal research report."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from quant4.services.multifractal.cli_support import default_cli_series
from quant4.services.multifractal.reports.multifractal_report import (
    build_multifractal_research_report,
)


class Command(BaseCommand):
    """Render a local Markdown research report."""

    help = "Generate a local Quant4 multifractal Markdown report."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register report command options."""
        parser.add_argument("--symbol", default="LOCAL")

    def handle(self, *args: object, **options: object) -> None:
        """Render a compact report."""
        report = build_multifractal_research_report(
            str(options["symbol"]),
            "cli_default_series",
            default_cli_series(),
        )
        self.stdout.write(report.to_markdown())
