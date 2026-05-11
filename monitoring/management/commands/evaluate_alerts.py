"""Evaluate in-app alert rules."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.alerts import evaluate_alert_rules
from monitoring.option_parsing import optional_int


class Command(BaseCommand):
    """Run enabled alert rules against recent documents."""

    help = "Evaluate in-app alert rules."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add alert lookback option."""
        parser.add_argument("--lookback-hours", type=int, default=24)

    def handle(self, *args: object, **options: object) -> None:
        """Execute alert evaluation."""
        lookback_hours = optional_int(options.get("lookback_hours")) or 24
        created_count = evaluate_alert_rules(lookback_hours=lookback_hours)
        self.stdout.write(f"Created {created_count} alert hits")
