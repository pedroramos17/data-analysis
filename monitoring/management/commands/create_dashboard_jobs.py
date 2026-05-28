"""Create dashboard PipelineJob rows from reusable templates."""

import json

from django.core.management.base import BaseCommand, CommandParser

from monitoring.orchestration.job_templates import create_dashboard_jobs


class Command(BaseCommand):
    """Create dashboard jobs from a named template."""

    help = "Create dashboard pipeline jobs from a reusable template."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add template creation options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--template", required=True)
        parser.add_argument("--profile", required=True)
        parser.add_argument("--partition", default="monthly")
        parser.add_argument("--provider", default="provider_neutral")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Create or preview template jobs.

        Example:
            `python manage.py create_dashboard_jobs --template local_simple_pipeline`
        """
        result = create_dashboard_jobs(
            str(options["template"]),
            str(options["profile"]),
            bool(options["dry_run"]),
            str(options["partition"]),
            str(options["provider"]),
        )
        self.stdout.write(json.dumps(result, indent=2))
