"""Score source reputation from local operational signals."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.option_parsing import optional_int
from monitoring.reputation import score_source_reputations


class Command(BaseCommand):
    """Compute and persist source reputation snapshots."""

    help = "Score source reputation over a rolling window."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add scoring window option."""
        parser.add_argument("--window-days", type=int, default=30)

    def handle(self, *args: object, **options: object) -> None:
        """Execute reputation scoring."""
        window_days = optional_int(options.get("window_days")) or 30
        updated_count = score_source_reputations(window_days=window_days)
        self.stdout.write(f"Scored {updated_count} sources")
