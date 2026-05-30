"""Build a lightweight financial relation graph."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from sourceflow.finance_graph.graph_builder import build_financial_graph


class Command(BaseCommand):
    """Build graph topology from a comma-separated universe."""

    help = "Build finance graph features from relation data."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register graph build options."""
        parser.add_argument("--symbols", default="")

    def handle(self, *args: object, **options: object) -> None:
        """Print graph node count."""
        symbols = [item for item in str(options["symbols"]).split(",") if item]
        graph = build_financial_graph(symbols, [])
        self.stdout.write(f"Financial graph nodes={graph.number_of_nodes()}")
