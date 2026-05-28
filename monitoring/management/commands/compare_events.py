"""Compute neutral event comparison snapshots."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.models import TopicCluster
from monitoring.option_parsing import optional_int
from monitoring.services.comparisons import compare_event_coverage


class Command(BaseCommand):
    """Compare provider and owner coverage across event clusters."""

    help = "Compute neutral event coverage comparison snapshots."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add comparison options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--omission-threshold", type=float, default=0.60)

    def handle(self, *args: object, **options: object) -> None:
        """Run comparison snapshots.

        Example:
            `python manage.py compare_events --limit 25`
        """
        limit = optional_int(options.get("limit")) or 100
        threshold = float(options["omission_threshold"])
        count = _compare_events(limit, threshold)
        self.stdout.write(f"Compared {count} events")


def _compare_events(limit: int, omission_threshold: float) -> int:
    events = TopicCluster.objects.filter(status=TopicCluster.Status.ACTIVE)[:limit]
    count = 0
    for event in events:
        compare_event_coverage(event, omission_threshold=omission_threshold)
        count += 1
    return count
