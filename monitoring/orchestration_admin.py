"""Admin registrations for dashboard orchestration state."""

from django.contrib import admin

from monitoring.orchestration_models import ResourceLock, WorkerHeartbeat


@admin.register(ResourceLock)
class ResourceLockAdmin(admin.ModelAdmin):
    """Admin view for active CPU/GPU/cloud resource locks."""

    list_display = (
        "resource_name",
        "locked_by_worker",
        "job",
        "expires_at",
        "heartbeat_at",
        "created_at",
    )
    list_filter = ("resource_name", "locked_by_worker")
    readonly_fields = ("created_at", "heartbeat_at")
    search_fields = ("resource_name", "locked_by_worker", "job__job_name")


@admin.register(WorkerHeartbeat)
class WorkerHeartbeatAdmin(admin.ModelAdmin):
    """Admin view for local dashboard worker heartbeats."""

    list_display = (
        "worker_id",
        "hostname",
        "profile",
        "backend",
        "status",
        "pid",
        "current_job",
        "last_heartbeat_at",
    )
    list_filter = ("profile", "backend", "status")
    readonly_fields = ("started_at", "last_heartbeat_at")
    search_fields = ("worker_id", "hostname", "current_job__job_name")
