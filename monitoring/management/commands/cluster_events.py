"""Cluster articles into event comparison groups."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.option_parsing import optional_int
from monitoring.services.events import cluster_articles_into_events


class Command(BaseCommand):
    """Build deterministic event clusters from articles."""

    help = "Cluster articles into explainable event groups."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add event clustering options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--window-hours", type=int, default=72)
        parser.add_argument("--min-link-score", type=float, default=0.50)
        parser.add_argument("--merge-score", type=float, default=0.85)

    def handle(self, *args: object, **options: object) -> None:
        """Run event clustering.

        Example:
            `python manage.py cluster_events --window-hours 24`
        """
        summary = cluster_articles_into_events(
            window_hours=optional_int(options.get("window_hours")) or 72,
            min_link_score=float(options["min_link_score"]),
            merge_score=float(options["merge_score"]),
        )
        self.stdout.write(
            _summary_line(summary.created_clusters, summary.linked_articles)
        )


def _summary_line(created_clusters: int, linked_articles: int) -> str:
    return (
        f"Clustered events; created {created_clusters} clusters and "
        f"linked {linked_articles} articles"
    )
