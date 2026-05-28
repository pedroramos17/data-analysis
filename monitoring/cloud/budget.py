"""Cloud budget guard and usage ledger operations."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from monitoring.dashboard_models import (
    CloudBudgetPolicy,
    CloudUsageLedger,
    PipelineJob,
)
from monitoring.orchestration.logging import append_job_event


@dataclass(frozen=True, slots=True)
class BudgetCheck:
    """Result of checking a job against one budget policy.

    Example:
        `check = check_budget_allowed(job, policy)`
    """

    allowed: bool
    status: str
    reason: str


def check_budget_allowed(job: PipelineJob, policy: CloudBudgetPolicy) -> BudgetCheck:
    """Check whether a cloud job can be queued under a policy.

    Example:
        `check_budget_allowed(job, policy).allowed`
    """
    if not policy.enabled:
        return _blocked("waiting_budget", "Budget policy is disabled")
    task_check = _task_allowed(job.task_name, policy)
    if task_check is not None:
        return task_check
    cost_check = _cost_allowed(job, policy)
    if cost_check is not None:
        return cost_check
    if _concurrent_cloud_jobs(policy) >= policy.max_concurrent_cloud_jobs:
        return _blocked("waiting_budget", "Concurrent cloud job limit reached")
    if policy.require_manual_approval and job.approved_at is None:
        return _blocked("waiting_approval", "Manual approval required")
    return BudgetCheck(True, "queued", "Budget guard passed")


def apply_budget_guard(job: PipelineJob, policy: CloudBudgetPolicy) -> BudgetCheck:
    """Apply budget status transitions to one cloud job.

    Example:
        `apply_budget_guard(job, policy)`
    """
    check = check_budget_allowed(job, policy)
    if check.allowed:
        job.status = PipelineJob.Status.QUEUED
        event_type = "queued"
    else:
        job.status = check.status
        event_type = _budget_event_type(check.status)
    job.save(update_fields=["status", "updated_at"])
    append_job_event(job, event_type, check.reason)
    return check


def record_estimated_usage(job: PipelineJob) -> CloudUsageLedger:
    """Record estimated cloud usage for a job.

    Example:
        `record_estimated_usage(job)`
    """
    return CloudUsageLedger.objects.create(
        provider=_job_provider(job),
        profile=job.profile,
        job=job,
        cost_estimated_usd=job.estimated_cost_usd,
        runtime_seconds=job.estimated_runtime_seconds,
        metadata_json={"kind": "estimated"},
    )


def record_actual_usage(
    job: PipelineJob,
    cost: Decimal,
    runtime: int,
) -> CloudUsageLedger:
    """Record actual cloud usage once a run completes.

    Example:
        `record_actual_usage(job, Decimal("1.25"), 3600)`
    """
    job.actual_cost_usd = cost
    job.save(update_fields=["actual_cost_usd", "updated_at"])
    return CloudUsageLedger.objects.create(
        provider=_job_provider(job),
        profile=job.profile,
        job=job,
        cost_actual_usd=cost,
        runtime_seconds=runtime,
        metadata_json={"kind": "actual"},
    )


def get_budget_summary(
    policy: CloudBudgetPolicy,
    date_range: tuple[date, date] | None = None,
) -> dict[str, object]:
    """Return estimated, actual, and remaining budget for a policy.

    Example:
        `get_budget_summary(policy)["remaining_total_usd"]`
    """
    entries = _ledger_entries(policy, date_range)
    daily_entries = _ledger_entries(policy, (timezone.localdate(), timezone.localdate()))
    estimated_total = _sum_decimal(entries, "cost_estimated_usd")
    actual_total = _sum_decimal(entries, "cost_actual_usd")
    estimated_daily = _sum_decimal(daily_entries, "cost_estimated_usd")
    return {
        "policy": policy.name,
        "provider": policy.provider,
        "max_total_cost_usd": str(policy.max_total_cost_usd),
        "max_daily_cost_usd": str(policy.max_daily_cost_usd),
        "estimated_used_usd": str(estimated_total),
        "actual_used_usd": str(actual_total),
        "estimated_daily_used_usd": str(estimated_daily),
        "remaining_total_usd": str(policy.max_total_cost_usd - estimated_total),
        "remaining_daily_usd": str(policy.max_daily_cost_usd - estimated_daily),
        "jobs_waiting_approval": _count_jobs(PipelineJob.Status.WAITING_APPROVAL),
        "jobs_blocked": _count_jobs(PipelineJob.Status.WAITING_BUDGET),
    }


def approve_cloud_job(job: PipelineJob, approved_by: str, note: str = "") -> PipelineJob:
    """Approve a cloud job and reapply budget guard.

    Example:
        `approve_cloud_job(job, "admin")`
    """
    job.approved_at = timezone.now()
    job.approved_by = approved_by
    job.approval_note = note
    job.save(update_fields=["approved_at", "approved_by", "approval_note", "updated_at"])
    policy = policy_for_job(job)
    apply_budget_guard(job, policy)
    return job


def block_cloud_job(job: PipelineJob, reason: str = "Cloud job blocked") -> PipelineJob:
    """Mark a cloud job as budget-blocked.

    Example:
        `block_cloud_job(job, "manual block")`
    """
    job.status = PipelineJob.Status.WAITING_BUDGET
    job.save(update_fields=["status", "updated_at"])
    append_job_event(job, "budget_blocked", reason)
    return job


def policy_for_job(job: PipelineJob) -> CloudBudgetPolicy:
    """Return the most specific enabled budget policy for a job.

    Example:
        `policy_for_job(job)`
    """
    provider = _job_provider(job)
    queryset = CloudBudgetPolicy.objects.filter(provider=provider)
    profile_policy = queryset.filter(profile=job.profile).first()
    if profile_policy is not None:
        return profile_policy
    policy = queryset.filter(profile__isnull=True).first()
    if policy is not None:
        return policy
    return _default_blocking_policy(provider, job)


def _task_allowed(task_name: str, policy: CloudBudgetPolicy) -> BudgetCheck | None:
    denied = set(_json_list(policy.denied_tasks_json))
    allowed = set(_json_list(policy.allowed_tasks_json))
    if task_name in denied:
        return _blocked("waiting_budget", f"Task {task_name} denied by policy")
    if allowed and task_name not in allowed:
        return _blocked("waiting_budget", f"Task {task_name} not in allowed tasks")
    return None


def _cost_allowed(job: PipelineJob, policy: CloudBudgetPolicy) -> BudgetCheck | None:
    cost = job.estimated_cost_usd
    if cost > policy.max_job_cost_usd:
        return _blocked("waiting_budget", "Estimated job cost exceeds max job cost")
    if _daily_estimated(policy) + cost > policy.max_daily_cost_usd:
        return _blocked("waiting_budget", "Daily cloud budget would be exceeded")
    if _total_estimated(policy) + cost > policy.max_total_cost_usd:
        return _blocked("waiting_budget", "Total cloud budget would be exceeded")
    return None


def _default_blocking_policy(provider: str, job: PipelineJob) -> CloudBudgetPolicy:
    policy, _created = CloudBudgetPolicy.objects.get_or_create(
        name=f"default blocking {provider}",
        defaults={
            "enabled": False,
            "provider": provider,
            "profile": job.profile,
            "require_manual_approval": True,
        },
    )
    return policy


def _ledger_entries(
    policy: CloudBudgetPolicy,
    date_range: tuple[date, date] | None,
) -> list[CloudUsageLedger]:
    queryset = CloudUsageLedger.objects.filter(provider=policy.provider)
    if policy.profile_id is not None:
        queryset = queryset.filter(profile=policy.profile)
    if date_range is not None:
        start, end = date_range
        queryset = queryset.filter(usage_date__gte=start, usage_date__lte=end)
    return list(queryset)


def _sum_decimal(entries: list[CloudUsageLedger], field_name: str) -> Decimal:
    total = Decimal("0")
    for entry in entries:
        total += getattr(entry, field_name)
    return total


def _daily_estimated(policy: CloudBudgetPolicy) -> Decimal:
    entries = _ledger_entries(policy, (timezone.localdate(), timezone.localdate()))
    return _sum_decimal(entries, "cost_estimated_usd")


def _total_estimated(policy: CloudBudgetPolicy) -> Decimal:
    entries = _ledger_entries(policy, None)
    return _sum_decimal(entries, "cost_estimated_usd")


def _concurrent_cloud_jobs(policy: CloudBudgetPolicy) -> int:
    queryset = PipelineJob.objects.filter(status=PipelineJob.Status.RUNNING)
    queryset = queryset.filter(backend="cloud", parameters_json__provider=policy.provider)
    return queryset.count()


def _job_provider(job: PipelineJob) -> str:
    return str(job.parameters_json.get("provider", "provider_neutral"))


def _json_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _blocked(status: str, reason: str) -> BudgetCheck:
    return BudgetCheck(False, status, reason)


def _budget_event_type(status: str) -> str:
    if status == PipelineJob.Status.WAITING_APPROVAL:
        return "approval_required"
    return "budget_blocked"


def _count_jobs(status: str) -> int:
    return PipelineJob.objects.filter(status=status, backend="cloud").count()
