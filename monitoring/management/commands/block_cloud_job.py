"""Block a cloud dashboard job from execution."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.cloud.budget import block_cloud_job
from monitoring.dashboard_models import PipelineJob


class Command(BaseCommand):
    """Mark one cloud job as budget-blocked."""

    help = "Block a cloud job and record a budget-blocked event."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add block options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--job-id", type=int, required=True)
        parser.add_argument("--reason", default="Blocked from CLI")

    def handle(self, *args: object, **options: object) -> None:
        """Block the requested cloud job.

        Example:
            `python manage.py block_cloud_job --job-id 123`
        """
        job = PipelineJob.objects.get(pk=int(options["job_id"]))
        block_cloud_job(job, str(options["reason"]))
        self.stdout.write(f"Job {job.pk} status={job.status}")
