"""Generate portable cloud job specs."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from monitoring.cloud.jobs import create_cloud_job_spec, write_cloud_job_spec


class Command(BaseCommand):
    """Write provider-neutral cloud job specs."""

    help = "Plan partitioned cloud jobs without provider SDKs."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add cloud job options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--task", required=True)
        parser.add_argument("--partition", default="monthly")
        parser.add_argument("--profile", default="cloud_student")
        parser.add_argument("--label", default="2024_01")
        parser.add_argument("--output", default="exports/cloud_jobs")

    def handle(self, *args: object, **options: object) -> None:
        """Write one cloud job spec.

        Example:
            `python manage.py plan_cloud_jobs --task mfdfa_gpu_batched`
        """
        spec = create_cloud_job_spec(
            str(options["task"]),
            str(options["profile"]),
            str(options["partition"]),
            str(options["label"]),
        )
        output_path = write_cloud_job_spec(spec, Path(str(options["output"])))
        self.stdout.write(f"Wrote {output_path}")

