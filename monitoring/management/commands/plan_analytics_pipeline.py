"""Plan analytics pipeline across local and cloud placements."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from monitoring.compute.planner import (
    plan_pipeline,
    render_plan_summary,
    write_plan_manifest,
)


class Command(BaseCommand):
    """Generate a local/cloud analytics pipeline plan."""

    help = "Plan analytics tasks without running expensive work."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add planner options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--profile", default="local_cpu_low")
        parser.add_argument("--advanced-target", default="cloud_student")
        parser.add_argument("--task", action="append", default=[])
        parser.add_argument("--rows", type=int, default=1000)
        parser.add_argument("--columns", type=int, default=16)
        parser.add_argument("--window", type=int, default=128)
        parser.add_argument("--batch-size", type=int, default=64)
        parser.add_argument("--output", default="exports/pipeline_plan.json")

    def handle(self, *args: object, **options: object) -> None:
        """Write a pipeline plan manifest and print a short summary.

        Example:
            `python manage.py plan_analytics_pipeline --profile local_cpu_low`
        """
        stats = _dataset_stats(options)
        plan = plan_pipeline(
            str(options["profile"]),
            list(options["task"]),
            stats,
            str(options["advanced_target"]),
        )
        output_path = write_plan_manifest(plan, Path(str(options["output"])))
        self.stdout.write(f"Wrote {output_path}: {render_plan_summary(plan)}")


def _dataset_stats(options: dict[str, object]) -> dict[str, object]:
    return {
        "rows": options["rows"],
        "columns": options["columns"],
        "window": options["window"],
        "batch_size": options["batch_size"],
    }

