"""Train a lightweight finance baseline model."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from sourceflow.finance_models.baselines import fit_ridge_baseline


class Command(BaseCommand):
    """Train a small baseline model without mandatory heavy dependencies."""

    help = "Train a finance baseline model."

    def handle(self, *args: object, **options: object) -> None:
        """Fit a tiny deterministic baseline and print model type."""
        model = fit_ridge_baseline([[1.0], [2.0]], [0.1, 0.2])
        self.stdout.write(f"Finance baseline model={model['model_type']}")
