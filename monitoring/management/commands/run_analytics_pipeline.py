"""Run or plan advanced analytics according to compute profile."""

from pathlib import Path
import json

from django.core.management.base import BaseCommand, CommandParser

from monitoring.analytics.pipeline import run_local_simple_pipeline
from monitoring.compute.planner import plan_pipeline, write_plan_manifest


class Command(BaseCommand):
    """Run RTX-local smoke work or plan cloud work for weaker profiles."""

    help = "Run advanced analytics only on RTX profile; otherwise write a plan."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add advanced analytics options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--profile", default="local_cpu_low")
        parser.add_argument("--backend", default="auto")
        parser.add_argument("--task", action="append", default=[])
        parser.add_argument("--batch-size", type=int, default=512)
        parser.add_argument("--window", type=int, default=512)
        parser.add_argument("--precision", default="float32")
        parser.add_argument("--max-vram-gb", type=float, default=None)
        parser.add_argument("--partition", default="")
        parser.add_argument("--output-dir", default="exports/analytics_run")

    def handle(self, *args: object, **options: object) -> None:
        """Run locally only for `local_rtx4060ti`; otherwise plan.

        Example:
            `python manage.py run_analytics_pipeline --profile local_rtx4060ti`
        """
        output_dir = Path(str(options["output_dir"]))
        if str(options["profile"]) != "local_rtx4060ti":
            path = _write_plan(options, output_dir)
            self.stdout.write(f"Wrote plan {path}; heavy work was not executed")
            return
        manifest = run_local_simple_pipeline("local_rtx4060ti", output_dir)
        _write_json(output_dir / "analytics_run_manifest.json", manifest)
        self.stdout.write(f"Wrote RTX local analytics smoke run to {output_dir}")


def _write_plan(options: dict[str, object], output_dir: Path) -> Path:
    stats = {
        "rows": 1000,
        "columns": 16,
        "window": options["window"],
        "batch_size": options["batch_size"],
        "precision": options["precision"],
        "max_vram_gb": options["max_vram_gb"] or "",
    }
    plan = plan_pipeline(str(options["profile"]), list(options["task"]), stats)
    return write_plan_manifest(plan, output_dir / "analytics_plan.json")


def _write_json(output_path: Path, payload: dict[str, object]) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path
