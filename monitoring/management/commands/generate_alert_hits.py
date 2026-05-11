"""Generate cluster-based alert hits."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.option_parsing import optional_int
from monitoring.services.alert_engine import generate_recent_alerts


class Command(BaseCommand):
    """Run the intelligent alert engine over recent event clusters."""

    help = "Generate alert hits from event clusters, rules, and detectors."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add alert generation options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--since-hours", type=int, default=24)
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: object, **options: object) -> None:
        """Execute alert generation and print a concise summary.

        Example:
            `python manage.py generate_alert_hits --since-hours 24`
        """
        since_hours = optional_int(options.get("since_hours")) or 24
        limit = optional_int(options.get("limit")) or 100
        dry_run = bool(options["dry_run"])
        alerts = generate_recent_alerts(since_hours, limit, dry_run)
        mode = "would create" if dry_run else "created"
        self.stdout.write(f"Alert engine {mode} {len(alerts)} alert hits")
