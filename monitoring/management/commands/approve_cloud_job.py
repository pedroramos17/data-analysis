"""Approve a cloud dashboard job after budget review."""

from django.core.management.base import BaseCommand, CommandParser

from monitoring.cloud.budget import approve_cloud_job
from monitoring.dashboard_models import PipelineJob


class Command(BaseCommand):
    """Approve one cloud job and reapply budget guard."""

    help = "Approve a cloud job if its budget policy permits it."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add approval options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--job-id", type=int, required=True)
        parser.add_argument("--approved-by", default="cli")
        parser.add_argument("--note", default="")

    def handle(self, *args: object, **options: object) -> None:
        """Approve the requested job.

        Example:
            `python manage.py approve_cloud_job --job-id 123`
        """
        job = PipelineJob.objects.get(pk=int(options["job_id"]))
        approve_cloud_job(job, str(options["approved_by"]), str(options["note"]))
        job.refresh_from_db()
        self.stdout.write(f"Job {job.pk} status={job.status}")
