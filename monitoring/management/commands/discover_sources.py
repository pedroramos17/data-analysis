"""Discover candidate public sources from normalized documents."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.discovery import discover_source_candidates
from monitoring.option_parsing import optional_int


class Command(BaseCommand):
    """Run the local source discovery pipeline."""

    help = "Discover source candidates without automatically enabling them."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add candidate scan limit."""
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args: object, **options: object) -> None:
        """Execute source discovery."""
        limit = optional_int(options.get("limit")) or 200
        created_count = discover_source_candidates(limit=limit)
        self.stdout.write(f"Discovered {created_count} source candidates")
