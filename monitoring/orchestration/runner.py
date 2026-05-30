"""Controlled subprocess runner for dashboard jobs."""

from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import TextIO
import os
import subprocess
import time

from django.conf import settings
from django.utils import timezone

from monitoring.dashboard_models import PipelineJob
from monitoring.orchestration.command_validation import validate_management_command
from monitoring.orchestration.locks import refresh_lock, release_lock
from monitoring.orchestration.logging import (
    append_job_event,
    append_log_line,
    ensure_job_log_path,
    update_progress_from_line,
)
from monitoring.orchestration.manifest import write_job_manifest
from monitoring.orchestration_models import ResourceLock


LineQueue = Queue[tuple[str, str]]


def run_job_subprocess(
    job: PipelineJob,
    lock: ResourceLock | None = None,
    worker_id: str = "worker",
) -> PipelineJob:
    """Run a validated management command and record logs/events.

    Example:
        `run_job_subprocess(job, lock, "cpu-1")`
    """
    warnings: list[str] = []
    errors: list[str] = []
    ensure_job_log_path(job)
    try:
        args = validate_management_command(job.command)
        _run_process(job, args, lock, worker_id, warnings, errors)
    except Exception as error:
        _mark_failed(job, str(error), errors)
    finally:
        release_lock(lock)
        job.refresh_from_db()
        write_job_manifest(job, warnings, errors)
    return job


def _run_process(
    job: PipelineJob,
    args: list[str],
    lock: ResourceLock | None,
    worker_id: str,
    warnings: list[str],
    errors: list[str],
) -> None:
    append_job_event(job, "started", f"Subprocess started by {worker_id}")
    process = subprocess.Popen(
        args,
        cwd=str(getattr(settings, "BASE_DIR", Path.cwd())),
        env=_job_env(job),
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line_queue = _start_stream_threads(process)
    _poll_process(job, process, line_queue, lock, warnings)
    _finalize_process(job, process.returncode or 0, errors)


def _start_stream_threads(process: subprocess.Popen[str]) -> LineQueue:
    line_queue: LineQueue = Queue()
    _start_reader(process.stdout, "stdout", line_queue)
    _start_reader(process.stderr, "stderr", line_queue)
    return line_queue


def _start_reader(stream: TextIO | None, stream_name: str, line_queue: LineQueue) -> None:
    if stream is None:
        return
    thread = Thread(target=_read_stream, args=(stream, stream_name, line_queue))
    thread.daemon = True
    thread.start()


def _read_stream(stream: TextIO, stream_name: str, line_queue: LineQueue) -> None:
    for line in stream:
        line_queue.put((stream_name, line.rstrip()))


def _poll_process(
    job: PipelineJob,
    process: subprocess.Popen[str],
    line_queue: LineQueue,
    lock: ResourceLock | None,
    warnings: list[str],
) -> None:
    while process.poll() is None:
        _drain_lines(job, line_queue, warnings)
        _refresh_running_lock(lock)
        if _should_stop_job(job):
            _terminate_process(process)
            return
        time.sleep(0.25)
    _drain_lines(job, line_queue, warnings)


def _drain_lines(
    job: PipelineJob,
    line_queue: LineQueue,
    warnings: list[str],
) -> None:
    while True:
        try:
            stream_name, line = line_queue.get_nowait()
        except Empty:
            return
        _record_process_line(job, stream_name, line, warnings)


def _record_process_line(
    job: PipelineJob,
    stream_name: str,
    line: str,
    warnings: list[str],
) -> None:
    append_log_line(job, stream_name, line)
    event_type = "stderr" if stream_name == "stderr" else "stdout"
    append_job_event(job, event_type, line)
    update_progress_from_line(job, line)
    if "out of memory" in line.lower() or "cuda oom" in line.lower():
        warnings.append(line)
        append_job_event(job, "warning", "GPU memory warning", {"line": line})


def _refresh_running_lock(lock: ResourceLock | None) -> None:
    if lock is not None:
        refresh_lock(lock)


def _should_stop_job(job: PipelineJob) -> bool:
    job.refresh_from_db(fields=["status"])
    return job.status in (PipelineJob.Status.CANCELLED, PipelineJob.Status.PAUSED)


def _terminate_process(process: subprocess.Popen[str]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _finalize_process(job: PipelineJob, return_code: int, errors: list[str]) -> None:
    job.refresh_from_db()
    if job.status in (PipelineJob.Status.CANCELLED, PipelineJob.Status.PAUSED):
        job.finished_at = timezone.now()
        job.save(update_fields=["finished_at", "updated_at"])
        event_type = "cancelled" if job.status == PipelineJob.Status.CANCELLED else "warning"
        append_job_event(job, event_type, f"Subprocess stopped as {job.status}")
        return
    job.finished_at = timezone.now()
    if return_code == 0:
        job.status = PipelineJob.Status.SUCCEEDED
        append_job_event(job, "succeeded", "Subprocess completed")
    else:
        job.status = PipelineJob.Status.FAILED
        job.error_message = f"Command exited with code {return_code}"
        errors.append(job.error_message)
        append_job_event(job, "failed", job.error_message)
    job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])


def _mark_failed(job: PipelineJob, message: str, errors: list[str]) -> None:
    job.status = PipelineJob.Status.FAILED
    job.error_message = message
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
    errors.append(message)
    append_job_event(job, "failed", message)


def _job_env(job: PipelineJob) -> dict[str, str]:
    env = os.environ.copy()
    env["DASHBOARD_JOB_ID"] = str(job.pk)
    env["DASHBOARD_JOB_PROFILE"] = job.profile.profile_type
    return env
