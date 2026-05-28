"""Inspect compute profile, capability, and backend routing state."""

import json
from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandParser

from monitoring.compute.capabilities import (
    ComputeCapabilities,
    detect_compute_capabilities,
)
from monitoring.compute.limits import apply_resource_limits, estimate_job_size
from monitoring.compute.native import detect_native_status
from monitoring.compute.profiles import get_compute_profile
from monitoring.compute.routing import select_backend


class Command(BaseCommand):
    """Print compute inspection JSON.

    Example:
        `python manage.py inspect_compute --profile local_cpu_low`
    """

    help = "Inspect compute profile limits and optional backend capabilities."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add profile and backend inspection options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--profile", default="local_cpu_low")
        parser.add_argument("--backend", default="auto")
        parser.add_argument("--task", default="")
        parser.add_argument("--native", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        """Print profile, capability, limits, backend, and native status JSON.

        Example:
            Django calls this after parsing command options.
        """
        profile_name = str(options["profile"])
        task_name = str(options["task"] or _default_task_for_profile(profile_name))
        capabilities = detect_compute_capabilities()
        payload = _inspection_payload(
            profile_name, task_name, str(options["backend"]), capabilities
        )
        if bool(options["native"]):
            payload["native"] = asdict(detect_native_status())
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))


def _inspection_payload(
    profile_name: str,
    task_name: str,
    backend_name: str,
    capabilities: ComputeCapabilities,
) -> dict[str, object]:
    profile = get_compute_profile(profile_name)
    selected = select_backend(task_name, backend_name, profile_name, capabilities)
    limited = apply_resource_limits({}, profile_name)
    estimate = estimate_job_size(
        1000, 16, profile.default_window, profile.default_batch_size, profile_name
    )
    return {
        "profile": asdict(profile),
        "capabilities": asdict(capabilities),
        "limits": limited,
        "selected_backend": asdict(selected),
        "sample_task": task_name,
        "sample_estimate": asdict(estimate),
    }


def _default_task_for_profile(profile_name: str) -> str:
    profile = get_compute_profile(profile_name)
    if profile.name == "local_cpu_low":
        return "ingestion"
    if profile.name == "local_mx350_queue":
        return "gpu_smoke_test"
    if profile.name == "local_rtx4060ti":
        return "wavelet_gpu"
    if profile.name == "cloud_student":
        return "advanced_dtcwt"
    return "partitioned_backfills"
