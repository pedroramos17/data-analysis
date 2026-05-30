"""Explain finance predictions with diagnostics-only payloads."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from sourceflow.finance_models.xai import finance_prediction_explanation


class Command(BaseCommand):
    """Return a finance prediction explanation envelope."""

    help = "Explain finance predictions with signal evidence and diagnostics."

    def handle(self, *args: object, **options: object) -> None:
        """Print the explanation boundary."""
        payload = finance_prediction_explanation({}, [], {})
        self.stdout.write(str(payload["boundary"]))
