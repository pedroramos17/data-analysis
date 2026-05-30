"""Run a local SQLite-backed dashboard worker."""

import time

from django.core.management.base import BaseCommand, CommandParser

from monitoring.orchestration.locks import cleanup_expired_locks
from monitoring.orchestration.runner import run_job_subprocess
from monitoring.orchestration.scheduler import claim_next_job
from monitoring.orchestration.worker_state import (
    heartbeat_worker,
    mark_stale_workers,
    register_worker,
    stop_worker,
)


class Command(BaseCommand):
    """Poll queued dashboard jobs and execute safe local commands."""

    help = "Run a local dashboard worker without Celery or Redis."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add dashboard worker options.

        Example:
            Django calls this before command execution.
        """
        parser.add_argument("--profile", default="local_cpu_low")
        parser.add_argument("--worker-id", default="")
        parser.add_argument("--backend", default="auto")
        parser.add_argument("--all-local", action="store_true")
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args: object, **options: object) -> None:
        """Run the worker loop.

        Example:
            `python manage.py dashboard_worker --profile local_cpu_low --once`
        """
        profile = "all-local" if options["all_local"] else str(options["profile"])
        worker_id = str(options["worker_id"] or f"{profile}-worker")
        register_worker(worker_id, profile, str(options["backend"]))
        try:
            self._run_loop(worker_id, profile, options)
        finally:
            stop_worker(worker_id)

    def _run_loop(
        self,
        worker_id: str,
        profile: str,
        options: dict[str, object],
    ) -> None:
        while True:
            cleanup_expired_locks()
            mark_stale_workers()
            claimed = claim_next_job(worker_id, profile)
            if claimed is None:
                heartbeat_worker(worker_id, "idle")
                if bool(options["once"]):
                    return
                time.sleep(float(options["poll_interval"]))
                continue
            job, lock = claimed
            heartbeat_worker(worker_id, "running", job)
            run_job_subprocess(job, lock, worker_id)
            heartbeat_worker(worker_id, "idle")
            if bool(options["once"]):
                return
