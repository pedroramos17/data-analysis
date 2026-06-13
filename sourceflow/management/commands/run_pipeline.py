"""Run the sourceflow document pipeline from the command line.

Examples:
    # start and run a new job end-to-end
    manage.py run_pipeline --source-id 1 --raw-text "Petrobras faces a regulatory investigation." --title "Probe"

    # run a single stage on an existing job (stages are independently runnable)
    manage.py run_pipeline --job 7 --stage extract_claims

    # retry a failed stage
    manage.py run_pipeline --job 7 --retry update_kg

    # show a job's visible state
    manage.py run_pipeline --status 7
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from sourceflow.orchestration import PipelineRunner, RetryPolicy, job_state


class Command(BaseCommand):
    help = "Run, single-step, retry, or inspect the sourceflow document pipeline."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--source-id", type=int, help="Source id for a new job")
        parser.add_argument("--raw-text", type=str, help="Raw document text for a new job")
        parser.add_argument("--title", type=str, default="")
        parser.add_argument("--url", type=str, default="")
        parser.add_argument("--job", type=int, help="Existing job id to act on")
        parser.add_argument("--stage", type=str, help="Run a single stage on --job")
        parser.add_argument("--retry", type=str, help="Retry a single stage on --job")
        parser.add_argument("--status", type=int, help="Print the visible state of a job id")
        parser.add_argument("--max-attempts", type=int, default=2, help="Retry attempts per stage")

    def handle(self, *args, **options) -> None:
        runner = PipelineRunner(retry_policy=RetryPolicy(max_attempts=options["max_attempts"]))

        if options.get("status"):
            self._emit(job_state(self._job(options["status"])))
            return

        stage = options.get("stage") or options.get("retry")
        if stage:
            if not options.get("job"):
                raise CommandError("--stage/--retry require --job")
            job = self._job(options["job"])
            run = runner.retry_stage(job, stage) if options.get("retry") else runner.run_stage(job, stage)
            self.stdout.write(f"stage {stage}: {run.status} (attempts={run.attempts})")
            self._emit(job_state(job))
            return

        if options.get("job"):
            job = self._job(options["job"])
        elif options.get("source_id") and options.get("raw_text") is not None:
            job = runner.create_job({
                "source_id": options["source_id"],
                "raw_text": options["raw_text"],
                "title": options.get("title", ""),
                "url": options.get("url", ""),
            })
        else:
            raise CommandError("start a new job with --source-id and --raw-text, or act on --job/--status")

        runner.run(job)
        self.stdout.write(self.style.SUCCESS(f"job {job.pk}: {job.status}"))
        self._emit(job_state(job))

    def _job(self, job_id: int):
        from sourceflow.models import PipelineJob

        try:
            return PipelineJob.objects.get(pk=job_id)
        except PipelineJob.DoesNotExist as exc:
            raise CommandError(f"job {job_id} not found") from exc

    def _emit(self, payload: dict) -> None:
        self.stdout.write(json.dumps(payload, indent=2, default=str))
