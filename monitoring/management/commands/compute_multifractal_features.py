"""Compute multifractal feature payloads from price lists."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.finance_features.multifractal.feature_builder import (
    build_multifractal_feature_set,
)


class Command(BaseCommand):
    """Compute a lightweight multifractal feature set."""

    help = "Compute multifractal, wavelet, and roughness features."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register price options."""
        parser.add_argument("--prices", required=True)

    def handle(self, *args: object, **options: object) -> None:
        """Parse prices and print feature keys."""
        prices = [float(value) for value in str(options["prices"]).split(",")]
        features = build_multifractal_feature_set(prices)
        self.stdout.write(f"Multifractal features={sorted(features)}")
