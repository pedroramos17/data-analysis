"""Print cloud budget summaries as JSON."""

import json

from django.core.management.base import BaseCommand, CommandParser

from monitoring.cloud.budget import get_budget_summary
from monitoring.dashboard_models import CloudBudgetPolicy


class Command(BaseCommand):
    """Show provider-neutral cloud budget usage."""

    help = "Print cloud budget summary JSON."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add budget summary options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--policy-id", type=int, default=0)

    def handle(self, *args: object, **options: object) -> None:
        """Write budget summary JSON to stdout.

        Example:
            `python manage.py cloud_budget_summary`
        """
        summaries = [_summary for _summary in self._summaries(int(options["policy_id"]))]
        self.stdout.write(json.dumps(summaries, indent=2))

    def _summaries(self, policy_id: int) -> list[dict[str, object]]:
        if policy_id:
            policy = CloudBudgetPolicy.objects.get(pk=policy_id)
            return [get_budget_summary(policy)]
        return [get_budget_summary(policy) for policy in CloudBudgetPolicy.objects.all()]
