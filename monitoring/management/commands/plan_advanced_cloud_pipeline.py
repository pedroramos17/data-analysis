"""Plan the advanced cloud-first analytics pipeline."""

from dataclasses import asdict
from pathlib import Path
import json

from django.core.management.base import BaseCommand, CommandParser

from monitoring.cloud.jobs import create_cloud_job_spec, write_cloud_job_spec
from monitoring.cloud.providers import render_provider_readme
from monitoring.compute.task_registry import advanced_cloud_tasks


class Command(BaseCommand):
    """Generate cloud job specs for advanced analytics tasks."""

    help = "Plan advanced cloud pipeline jobs and instructions."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add advanced cloud planning options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--local-profile", default="local_cpu_low")
        parser.add_argument("--cloud-profile", default="cloud_student")
        parser.add_argument("--partition", default="monthly")
        parser.add_argument("--output-dir", default="exports/cloud_plan")

    def handle(self, *args: object, **options: object) -> None:
        """Write cloud pipeline manifest, jobs, and provider instructions.

        Example:
            `python manage.py plan_advanced_cloud_pipeline --partition monthly`
        """
        output_dir = Path(str(options["output_dir"]))
        job_dir = output_dir / "jobs"
        specs = _write_specs(
            job_dir, str(options["cloud_profile"]), str(options["partition"])
        )
        manifest = _pipeline_manifest(options, specs)
        _write_json(output_dir / "cloud_pipeline_manifest.json", manifest)
        readme_path = output_dir / "README_RUN_CLOUD.md"
        readme_path.write_text(render_provider_readme(), encoding="utf-8")
        self.stdout.write(f"Wrote advanced cloud plan to {output_dir}")


def _write_specs(
    job_dir: Path, cloud_profile: str, partition: str
) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for task_name in advanced_cloud_tasks():
        spec = create_cloud_job_spec(task_name, cloud_profile, partition, "2024_01")
        write_cloud_job_spec(spec, job_dir)
        specs.append(asdict(spec))
    return specs


def _pipeline_manifest(
    options: dict[str, object], specs: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "local_profile": str(options["local_profile"]),
        "cloud_profile": str(options["cloud_profile"]),
        "partition": str(options["partition"]),
        "jobs": specs,
        "heavy_work_executed": False,
    }


def _write_json(output_path: Path, payload: dict[str, object]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path
