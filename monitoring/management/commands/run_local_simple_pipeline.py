"""Run the safe local-only analytics pipeline."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser

from monitoring.analytics.pipeline import run_local_simple_pipeline


class Command(BaseCommand):
    """Run simple analytics tasks without cloud or heavy training."""

    help = "Run local simple analytics pipeline with profile limits."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add local simple pipeline options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--profile", default="local_cpu_low")
        parser.add_argument("--output-dir", default="exports/local_simple")
        parser.add_argument("--enable-micro-gpu", action="store_true")
        parser.add_argument("--max-vram-gb", type=float, default=None)
        parser.add_argument("--queue", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Run the bounded local simple pipeline.

        Example:
            `python manage.py run_local_simple_pipeline --profile local_cpu_low`
        """
        manifest = run_local_simple_pipeline(
            str(options["profile"]),
            Path(str(options["output_dir"])),
            bool(options["enable_micro_gpu"]),
            options["max_vram_gb"],
            bool(options["queue"]),
        )
        manifest_path = Path(str(options["output_dir"])) / "local_simple_manifest.json"
        task_count = len(manifest["tasks"])
        self.stdout.write(f"Wrote {manifest_path} with {task_count} local tasks")
