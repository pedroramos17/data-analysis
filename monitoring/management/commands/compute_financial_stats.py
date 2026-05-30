"""Compute finance statistical scores."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.finance_stats.hm_correlation import hm_corrected_corr
from sourceflow.finance_stats.melao_index import melao_inspired_score


class Command(BaseCommand):
    """Compute HM correlation and Melao-inspired examples."""

    help = "Compute finance statistical scores."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register metric options."""
        parser.add_argument("--equity", default="100,101,102")

    def handle(self, *args: object, **options: object) -> None:
        """Print example metric values."""
        equity = [float(value) for value in str(options["equity"]).split(",")]
        hm = hm_corrected_corr(0.4, 1.0, 1.0, 2.0, 2.0)
        self.stdout.write(f"hm={hm:.6f} melao={melao_inspired_score(equity):.6f}")
