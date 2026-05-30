"""Build static global market window definitions."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from sourceflow.finance_ingestion.global_market_windows import market_windows


class Command(BaseCommand):
    """Print built-in exchange windows."""

    help = "Build static global market session windows."

    def handle(self, *args: object, **options: object) -> None:
        """Print supported exchange count."""
        self.stdout.write(f"Market windows={len(market_windows())}")
