"""Cluster documents into deterministic local topics."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.option_parsing import optional_int
from monitoring.topics import cluster_topics


class Command(BaseCommand):
    """Build rolling-window topic clusters."""

    help = "Build deterministic local topic clusters."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add clustering window and minimum size options."""
        parser.add_argument("--window-hours", type=int, default=72)
        parser.add_argument("--min-documents", type=int, default=3)

    def handle(self, *args: object, **options: object) -> None:
        """Execute topic clustering."""
        window_hours = optional_int(options.get("window_hours")) or 72
        min_documents = optional_int(options.get("min_documents")) or 3
        cluster_count = cluster_topics(
            window_hours=window_hours, min_documents=min_documents
        )
        self.stdout.write(f"Built {cluster_count} topic clusters")
