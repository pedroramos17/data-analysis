"""Build finance prediction dataset manifests."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.finance_dataset.manifests import build_manifest


class Command(BaseCommand):
    """Build a prediction dataset manifest."""

    help = "Build a leakage-controlled finance prediction dataset."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register dataset options."""
        parser.add_argument("--name", default="finance-demo")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Print manifest summary."""
        manifest = build_manifest(str(options["name"]), [], "forward_return", "")
        self.stdout.write(f"Prediction dataset {manifest['name']} rows=0")
