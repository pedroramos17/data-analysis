"""Retrying ingestion service for source registry entries."""

import logging
import time
from dataclasses import dataclass

from django.utils import timezone

from monitoring.adapters import build_source_adapter
from monitoring.contracts import FetchedRecord, IngestionSummary
from monitoring.health import (
    record_checkpoint_failure,
    record_checkpoint_success,
    source_is_in_cooldown,
)
from monitoring.models import FetchJob, Source
from monitoring.storage import persist_fetched_record, store_dead_letter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry settings for transient ingestion failures.

    Example:
        `RetryPolicy(max_attempts=3, base_delay_seconds=1.0)`
    """

    max_attempts: int = 3
    base_delay_seconds: float = 1.0


class IngestionService:
    """Fetch, parse, normalize, and store one source idempotently.

    Example:
        `IngestionService().ingest_source(source, limit=50)`
    """

    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        self.retry_policy = retry_policy or RetryPolicy()

    def ingest_source(
        self, source: Source, limit: int | None = None
    ) -> IngestionSummary:
        """Ingest one source with bounded retries and checkpoint updates.

        Example:
            `summary = service.ingest_source(source, limit=20)`
        """
        if source_is_in_cooldown(source):
            return _skipped_summary(source)
        job = _start_job(source)
        try:
            summary = self._ingest_with_retries(job, source, limit)
        except Exception as error:
            _fail_job(job, error)
            _record_source_failure(source, error)
            raise
        _succeed_job(job, summary)
        return summary

    def _ingest_with_retries(
        self,
        job: FetchJob,
        source: Source,
        limit: int | None,
    ) -> IngestionSummary:
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            _set_job_attempt(job, attempt)
            try:
                return _ingest_once(source, limit)
            except Exception:
                if attempt == self.retry_policy.max_attempts:
                    raise
                time.sleep(calculate_backoff(attempt, self.retry_policy))
        raise RuntimeError(_retry_policy_error(self.retry_policy))


def calculate_backoff(attempt: int, retry_policy: RetryPolicy) -> float:
    """Return exponential backoff for an attempt number.

    Example:
        `calculate_backoff(2, RetryPolicy(base_delay_seconds=1.0))`
    """
    if attempt < 1:
        raise ValueError(f"Invalid attempt {attempt!r}; expected positive integer")
    return retry_policy.base_delay_seconds * (2 ** (attempt - 1))


def _ingest_once(source: Source, limit: int | None) -> IngestionSummary:
    adapter = build_source_adapter(source)
    fetched_records = adapter.fetch_records(limit=limit)
    summary = _persist_fetched_records(source, fetched_records)
    record_checkpoint_success(
        source, summary.parsed_count, _last_http_status(fetched_records)
    )
    logger.info("source_ingested", extra=_summary_log(summary))
    return summary


def _persist_fetched_records(
    source: Source,
    fetched_records: list[FetchedRecord],
) -> IngestionSummary:
    raw_created_count = 0
    document_created_count = 0
    failed_count = 0
    for fetched_record in fetched_records:
        raw_created, doc_created, failed = _persist_or_dead_letter(
            source, fetched_record
        )
        raw_created_count += int(raw_created)
        document_created_count += int(doc_created)
        failed_count += int(failed)
    duplicate_count = len(fetched_records) - document_created_count - failed_count
    return IngestionSummary(
        source.id or 0,
        len(fetched_records),
        raw_created_count,
        document_created_count,
        duplicate_count,
        failed_count,
    )


def _persist_or_dead_letter(
    source: Source,
    fetched_record: FetchedRecord,
) -> tuple[bool, bool, bool]:
    try:
        raw_created, doc_created = persist_fetched_record(source, fetched_record)
    except Exception as error:
        _store_record_failure(source, fetched_record, error)
        return False, False, True
    return raw_created, doc_created, False


def _store_record_failure(
    source: Source,
    fetched_record: FetchedRecord,
    error: Exception,
) -> None:
    record = fetched_record.parsed_record
    url = record.url or fetched_record.fetch_result.url
    store_dead_letter(source, url, str(error), record.content)


def _start_job(source: Source) -> FetchJob:
    return FetchJob.objects.create(
        source=source,
        status=FetchJob.Status.RUNNING,
        attempts=1,
        started_at=timezone.now(),
    )


def _set_job_attempt(job: FetchJob, attempt: int) -> None:
    job.attempts = attempt
    job.save(update_fields=["attempts"])


def _succeed_job(job: FetchJob, summary: IngestionSummary) -> None:
    job.status = FetchJob.Status.SUCCEEDED
    job.finished_at = timezone.now()
    job.metrics = _summary_log(summary)
    job.save(update_fields=["status", "finished_at", "metrics"])


def _fail_job(job: FetchJob, error: Exception) -> None:
    job.status = FetchJob.Status.FAILED
    job.finished_at = timezone.now()
    job.error_message = str(error)
    job.save(update_fields=["status", "finished_at", "error_message"])


def _record_source_failure(source: Source, error: Exception) -> None:
    store_dead_letter(source, source.url, str(error))
    record_checkpoint_failure(source, error)


def _last_http_status(fetched_records: list[FetchedRecord]) -> int | None:
    if not fetched_records:
        return None
    return fetched_records[-1].fetch_result.status_code


def _skipped_summary(source: Source) -> IngestionSummary:
    return IngestionSummary(source.id or 0, 0, 0, 0, 0, 0)


def _summary_log(summary: IngestionSummary) -> dict[str, object]:
    return {
        "source_id": summary.source_id,
        "parsed_count": summary.parsed_count,
        "raw_created_count": summary.raw_created_count,
        "document_created_count": summary.document_created_count,
        "duplicate_count": summary.duplicate_count,
        "failed_count": summary.failed_count,
    }


def _retry_policy_error(retry_policy: RetryPolicy) -> str:
    return f"Invalid retry policy {retry_policy!r}; expected at least one attempt"
