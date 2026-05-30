"""Operational dashboard models for local and cloud job control."""

from django.db import models
from django.utils import timezone


class ComputeProfileTypeSetting(models.Model):
    """Editable compute profile type seed and policy metadata.

    Example:
        `ComputeProfileTypeSetting.objects.get(slug="local_cpu_low")`
    """

    slug = models.SlugField(max_length=80, unique=True)
    label = models.CharField(max_length=120)
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    backend_preference = models.CharField(max_length=32, default="auto")
    allow_cpu = models.BooleanField(default=True)
    allow_gpu = models.BooleanField(default=False)
    allow_cloud = models.BooleanField(default=False)
    allow_ctypes = models.BooleanField(default=True)
    max_vram_gb = models.FloatField(default=0)
    max_ram_gb = models.FloatField(null=True, blank=True)
    default_batch_size = models.PositiveIntegerField(default=64)
    max_batch_size = models.PositiveIntegerField(default=256)
    default_window = models.PositiveIntegerField(default=128)
    max_window = models.PositiveIntegerField(default=512)
    default_precision = models.CharField(max_length=16, default="float32")
    allowed_tasks_json = models.JSONField(default=list, blank=True)
    denied_tasks_json = models.JSONField(default=list, blank=True)
    queue_enabled = models.BooleanField(default=True)
    max_runtime_hours = models.FloatField(default=2.0)
    budget_guard_enabled = models.BooleanField(default=False)
    notes_json = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug"]
        indexes = [
            models.Index(fields=["enabled", "slug"], name="dash_ptype_enabled_idx"),
            models.Index(fields=["allow_cloud", "enabled"], name="dash_ptype_cloud_idx"),
        ]

    def __str__(self) -> str:
        """Return the profile type slug.

        Example:
            `str(profile_type)` returns `local_cpu_low`.
        """
        return self.slug


class ComputeProfileConfig(models.Model):
    """Editable runtime limits for one dashboard compute profile.

    Example:
        `ComputeProfileConfig.objects.get(profile_type="local_cpu_low")`
    """

    class BackendPreference(models.TextChoices):
        AUTO = "auto", "Auto"
        CPU = "cpu", "CPU"
        GPU = "gpu", "GPU"
        CLOUD = "cloud", "Cloud"

    name = models.CharField(max_length=120, unique=True)
    profile_type = models.CharField(max_length=80)
    enabled = models.BooleanField(default=True)
    backend_preference = models.CharField(
        max_length=16,
        choices=BackendPreference.choices,
        default=BackendPreference.AUTO,
    )
    max_cpu_workers = models.PositiveSmallIntegerField(default=1)
    max_gpu_workers = models.PositiveSmallIntegerField(default=0)
    max_vram_gb = models.FloatField(default=0)
    max_ram_gb = models.FloatField(default=0)
    default_batch_size = models.PositiveIntegerField(default=64)
    max_batch_size = models.PositiveIntegerField(default=256)
    default_window = models.PositiveIntegerField(default=128)
    max_window = models.PositiveIntegerField(default=512)
    default_precision = models.CharField(max_length=16, default="float32")
    queue_enabled = models.BooleanField(default=True)
    cloud_enabled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["enabled", "profile_type"],
                name="dash_profile_enabled_idx",
            ),
            models.Index(
                fields=["cloud_enabled", "profile_type"],
                name="dash_profile_cloud_idx",
            ),
        ]

    def __str__(self) -> str:
        """Return a compact dashboard label.

        Example:
            `str(profile)` returns `local_cpu_low`.
        """
        return self.name


class ComputeResourceSnapshot(models.Model):
    """Point-in-time CPU, GPU, and optional backend capability report.

    Example:
        `ComputeResourceSnapshot.objects.latest("captured_at")`
    """

    profile = models.ForeignKey(
        ComputeProfileConfig,
        null=True,
        blank=True,
        related_name="resource_snapshots",
        on_delete=models.SET_NULL,
    )
    hostname = models.CharField(max_length=255)
    cpu_count = models.PositiveIntegerField(default=0)
    ram_total_gb = models.FloatField(null=True, blank=True)
    ram_available_gb = models.FloatField(null=True, blank=True)
    gpu_available = models.BooleanField(default=False)
    gpu_name = models.CharField(max_length=255, blank=True)
    gpu_count = models.PositiveSmallIntegerField(default=0)
    gpu_total_vram_gb = models.FloatField(null=True, blank=True)
    gpu_free_vram_gb = models.FloatField(null=True, blank=True)
    torch_available = models.BooleanField(default=False)
    cuda_available = models.BooleanField(default=False)
    cupy_available = models.BooleanField(default=False)
    native_ctypes_available = models.BooleanField(default=False)
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-captured_at"]
        indexes = [
            models.Index(
                fields=["profile", "captured_at"],
                name="dash_resource_profile_idx",
            ),
            models.Index(
                fields=["hostname", "captured_at"],
                name="dash_resource_host_idx",
            ),
            models.Index(
                fields=["gpu_available", "captured_at"],
                name="dash_resource_gpu_idx",
            ),
        ]

    def __str__(self) -> str:
        """Return the host and capture timestamp.

        Example:
            `str(snapshot)` includes the hostname.
        """
        return f"{self.hostname} at {self.captured_at.isoformat()}"


class PipelineJob(models.Model):
    """Queued or historical pipeline task controlled by the dashboard.

    Example:
        `PipelineJob.objects.filter(status=PipelineJob.Status.QUEUED)`
    """

    class Backend(models.TextChoices):
        AUTO = "auto", "Auto"
        CPU = "cpu", "CPU"
        GPU = "gpu", "GPU"
        CLOUD = "cloud", "Cloud"
        CUDA = "cuda", "CUDA"
        CUPY = "cupy", "CuPy"
        NATIVE = "native", "Native"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        PAUSED = "paused", "Paused"
        WAITING_BUDGET = "waiting_budget", "Waiting budget"
        WAITING_APPROVAL = "waiting_approval", "Waiting approval"
        WAITING_RESOURCE = "waiting_resource", "Waiting resource"

    job_name = models.CharField(max_length=180)
    task_name = models.CharField(max_length=120)
    profile = models.ForeignKey(
        ComputeProfileConfig,
        related_name="pipeline_jobs",
        on_delete=models.PROTECT,
    )
    backend = models.CharField(
        max_length=20,
        choices=Backend.choices,
        default=Backend.AUTO,
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    priority = models.IntegerField(default=100)
    command = models.TextField(blank=True)
    parameters_json = models.JSONField(default=dict, blank=True)
    input_artifacts_json = models.JSONField(default=dict, blank=True)
    output_artifacts_json = models.JSONField(default=dict, blank=True)
    manifest_path = models.CharField(max_length=1200, blank=True)
    log_path = models.CharField(max_length=1200, blank=True)
    progress_current = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    progress_percent = models.FloatField(default=0)
    estimated_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
    )
    actual_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
    )
    estimated_runtime_seconds = models.PositiveIntegerField(default=0)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.CharField(max_length=150, blank=True)
    approval_note = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["priority", "-created_at"]
        indexes = [
            models.Index(fields=["status", "priority"], name="dash_job_status_idx"),
            models.Index(fields=["profile", "status"], name="dash_job_profile_idx"),
            models.Index(fields=["task_name", "status"], name="dash_job_task_idx"),
            models.Index(fields=["backend", "status"], name="dash_job_backend_idx"),
            models.Index(fields=["created_at"], name="dash_job_created_idx"),
        ]

    def __str__(self) -> str:
        """Return the job display name.

        Example:
            `str(job)` returns the name shown in the queue.
        """
        return self.job_name


class JobRunEvent(models.Model):
    """Append-only event stream for a dashboard pipeline job.

    Example:
        `JobRunEvent.objects.create(job=job, event_type="queued")`
    """

    class EventType(models.TextChoices):
        CREATED = "created", "Created"
        QUEUED = "queued", "Queued"
        STARTED = "started", "Started"
        PROGRESS = "progress", "Progress"
        STDOUT = "stdout", "Stdout"
        STDERR = "stderr", "Stderr"
        WARNING = "warning", "Warning"
        FAILED = "failed", "Failed"
        SUCCEEDED = "succeeded", "Succeeded"
        CANCELLED = "cancelled", "Cancelled"
        BUDGET_BLOCKED = "budget_blocked", "Budget blocked"
        APPROVAL_REQUIRED = "approval_required", "Approval required"
        RESOURCE_BLOCKED = "resource_blocked", "Resource blocked"

    job = models.ForeignKey(
        PipelineJob,
        related_name="run_events",
        on_delete=models.CASCADE,
    )
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    message = models.TextField(blank=True)
    payload_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["job", "created_at"], name="dash_event_job_idx"),
            models.Index(
                fields=["event_type", "created_at"],
                name="dash_event_type_idx",
            ),
        ]

    def __str__(self) -> str:
        """Return a compact event label.

        Example:
            `str(event)` includes the job id and event type.
        """
        return f"{self.job_id}:{self.event_type}"


class CloudBudgetPolicy(models.Model):
    """Provider-neutral budget and approval policy for cloud jobs.

    Example:
        `CloudBudgetPolicy.objects.filter(enabled=True)`
    """

    name = models.CharField(max_length=120, unique=True)
    enabled = models.BooleanField(default=True)
    provider = models.CharField(max_length=80, default="provider_neutral")
    profile = models.ForeignKey(
        ComputeProfileConfig,
        null=True,
        blank=True,
        related_name="cloud_budget_policies",
        on_delete=models.SET_NULL,
    )
    max_total_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
    )
    max_daily_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
    )
    max_job_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
    )
    max_runtime_hours_per_job = models.FloatField(default=4.0)
    max_concurrent_cloud_jobs = models.PositiveSmallIntegerField(default=1)
    allowed_tasks_json = models.JSONField(default=list, blank=True)
    denied_tasks_json = models.JSONField(default=list, blank=True)
    require_manual_approval = models.BooleanField(default=True)
    stop_when_reached = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["enabled", "provider"],
                name="dash_budget_enabled_idx",
            ),
            models.Index(
                fields=["profile", "enabled"],
                name="dash_budget_profile_idx",
            ),
        ]

    def __str__(self) -> str:
        """Return the budget policy name.

        Example:
            `str(policy)` returns `student credits guard`.
        """
        return self.name


class CloudUsageLedger(models.Model):
    """Estimated and actual cloud usage recorded for budget summaries.

    Example:
        `CloudUsageLedger.objects.filter(provider="gcp")`
    """

    provider = models.CharField(max_length=80)
    profile = models.ForeignKey(
        ComputeProfileConfig,
        null=True,
        blank=True,
        related_name="cloud_usage_entries",
        on_delete=models.SET_NULL,
    )
    job = models.ForeignKey(
        PipelineJob,
        null=True,
        blank=True,
        related_name="cloud_usage_entries",
        on_delete=models.SET_NULL,
    )
    cost_estimated_usd = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
    )
    cost_actual_usd = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        default=0,
    )
    runtime_seconds = models.PositiveIntegerField(default=0)
    usage_date = models.DateField(default=timezone.localdate)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-usage_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["provider", "usage_date"],
                name="dash_usage_provider_idx",
            ),
            models.Index(
                fields=["profile", "usage_date"],
                name="dash_usage_profile_idx",
            ),
            models.Index(fields=["job", "usage_date"], name="dash_usage_job_idx"),
        ]

    def __str__(self) -> str:
        """Return the provider and usage date.

        Example:
            `str(entry)` returns a provider/date label.
        """
        return f"{self.provider}:{self.usage_date.isoformat()}"


class DashboardSetting(models.Model):
    """Small JSON-backed setting used by dashboard pages and workers.

    Example:
        `DashboardSetting.objects.get(key="dashboard.refresh_seconds")`
    """

    key = models.CharField(max_length=120, unique=True)
    value_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        """Return the setting key.

        Example:
            `str(setting)` returns `dashboard.refresh_seconds`.
        """
        return self.key
