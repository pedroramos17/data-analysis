# Generated manually because this environment does not have Django installed.

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0007_ingestionrun_marketinstrument_ingesteditem_marketbar_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ComputeProfileConfig",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, unique=True)),
                (
                    "profile_type",
                    models.CharField(
                        choices=[
                            ("local_cpu_low", "Local CPU low"),
                            ("local_mx350_queue", "Local MX350 queue"),
                            ("local_rtx4060ti", "Local RTX 4060 Ti"),
                            ("cloud_student", "Cloud student"),
                            (
                                "cloud_serverless_on_demand",
                                "Cloud serverless",
                            ),
                        ],
                        max_length=40,
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
                (
                    "backend_preference",
                    models.CharField(
                        choices=[
                            ("auto", "Auto"),
                            ("cpu", "CPU"),
                            ("gpu", "GPU"),
                            ("cloud", "Cloud"),
                        ],
                        default="auto",
                        max_length=16,
                    ),
                ),
                ("max_cpu_workers", models.PositiveSmallIntegerField(default=1)),
                ("max_gpu_workers", models.PositiveSmallIntegerField(default=0)),
                ("max_vram_gb", models.FloatField(default=0)),
                ("max_ram_gb", models.FloatField(default=0)),
                ("default_batch_size", models.PositiveIntegerField(default=64)),
                ("max_batch_size", models.PositiveIntegerField(default=256)),
                ("default_window", models.PositiveIntegerField(default=128)),
                ("max_window", models.PositiveIntegerField(default=512)),
                ("default_precision", models.CharField(default="float32", max_length=16)),
                ("queue_enabled", models.BooleanField(default=True)),
                ("cloud_enabled", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
                "indexes": [
                    models.Index(
                        fields=["enabled", "profile_type"],
                        name="dash_profile_enabled_idx",
                    ),
                    models.Index(
                        fields=["cloud_enabled", "profile_type"],
                        name="dash_profile_cloud_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DashboardSetting",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(max_length=120, unique=True)),
                ("value_json", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["key"]},
        ),
        migrations.CreateModel(
            name="ComputeResourceSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("hostname", models.CharField(max_length=255)),
                ("cpu_count", models.PositiveIntegerField(default=0)),
                ("ram_total_gb", models.FloatField(blank=True, null=True)),
                ("ram_available_gb", models.FloatField(blank=True, null=True)),
                ("gpu_available", models.BooleanField(default=False)),
                ("gpu_name", models.CharField(blank=True, max_length=255)),
                ("gpu_count", models.PositiveSmallIntegerField(default=0)),
                ("gpu_total_vram_gb", models.FloatField(blank=True, null=True)),
                ("gpu_free_vram_gb", models.FloatField(blank=True, null=True)),
                ("torch_available", models.BooleanField(default=False)),
                ("cuda_available", models.BooleanField(default=False)),
                ("cupy_available", models.BooleanField(default=False)),
                ("native_ctypes_available", models.BooleanField(default=False)),
                ("captured_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resource_snapshots",
                        to="monitoring.computeprofileconfig",
                    ),
                ),
            ],
            options={
                "ordering": ["-captured_at"],
                "indexes": [
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
                ],
            },
        ),
        migrations.CreateModel(
            name="PipelineJob",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("job_name", models.CharField(max_length=180)),
                ("task_name", models.CharField(max_length=120)),
                (
                    "backend",
                    models.CharField(
                        choices=[
                            ("auto", "Auto"),
                            ("cpu", "CPU"),
                            ("gpu", "GPU"),
                            ("cloud", "Cloud"),
                            ("cuda", "CUDA"),
                            ("cupy", "CuPy"),
                            ("native", "Native"),
                        ],
                        default="auto",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("cancelled", "Cancelled"),
                            ("paused", "Paused"),
                            ("waiting_budget", "Waiting budget"),
                            ("waiting_approval", "Waiting approval"),
                            ("waiting_resource", "Waiting resource"),
                        ],
                        default="draft",
                        max_length=32,
                    ),
                ),
                ("priority", models.IntegerField(default=100)),
                ("command", models.TextField(blank=True)),
                ("parameters_json", models.JSONField(blank=True, default=dict)),
                ("input_artifacts_json", models.JSONField(blank=True, default=dict)),
                ("output_artifacts_json", models.JSONField(blank=True, default=dict)),
                ("manifest_path", models.CharField(blank=True, max_length=1200)),
                ("log_path", models.CharField(blank=True, max_length=1200)),
                ("progress_current", models.PositiveIntegerField(default=0)),
                ("progress_total", models.PositiveIntegerField(default=0)),
                ("progress_percent", models.FloatField(default=0)),
                (
                    "estimated_cost_usd",
                    models.DecimalField(decimal_places=4, default=0, max_digits=12),
                ),
                (
                    "actual_cost_usd",
                    models.DecimalField(decimal_places=4, default=0, max_digits=12),
                ),
                ("estimated_runtime_seconds", models.PositiveIntegerField(default=0)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", models.CharField(blank=True, max_length=150)),
                ("approval_note", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("error_message", models.TextField(blank=True)),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pipeline_jobs",
                        to="monitoring.computeprofileconfig",
                    ),
                ),
            ],
            options={
                "ordering": ["priority", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["status", "priority"],
                        name="dash_job_status_idx",
                    ),
                    models.Index(
                        fields=["profile", "status"],
                        name="dash_job_profile_idx",
                    ),
                    models.Index(
                        fields=["task_name", "status"],
                        name="dash_job_task_idx",
                    ),
                    models.Index(
                        fields=["backend", "status"],
                        name="dash_job_backend_idx",
                    ),
                    models.Index(fields=["created_at"], name="dash_job_created_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="CloudBudgetPolicy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, unique=True)),
                ("enabled", models.BooleanField(default=True)),
                ("provider", models.CharField(default="provider_neutral", max_length=80)),
                (
                    "max_total_cost_usd",
                    models.DecimalField(decimal_places=4, default=0, max_digits=12),
                ),
                (
                    "max_daily_cost_usd",
                    models.DecimalField(decimal_places=4, default=0, max_digits=12),
                ),
                (
                    "max_job_cost_usd",
                    models.DecimalField(decimal_places=4, default=0, max_digits=12),
                ),
                ("max_runtime_hours_per_job", models.FloatField(default=4.0)),
                ("max_concurrent_cloud_jobs", models.PositiveSmallIntegerField(default=1)),
                ("allowed_tasks_json", models.JSONField(blank=True, default=list)),
                ("denied_tasks_json", models.JSONField(blank=True, default=list)),
                ("require_manual_approval", models.BooleanField(default=True)),
                ("stop_when_reached", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cloud_budget_policies",
                        to="monitoring.computeprofileconfig",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "indexes": [
                    models.Index(
                        fields=["enabled", "provider"],
                        name="dash_budget_enabled_idx",
                    ),
                    models.Index(
                        fields=["profile", "enabled"],
                        name="dash_budget_profile_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="CloudUsageLedger",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("provider", models.CharField(max_length=80)),
                (
                    "cost_estimated_usd",
                    models.DecimalField(decimal_places=4, default=0, max_digits=12),
                ),
                (
                    "cost_actual_usd",
                    models.DecimalField(decimal_places=4, default=0, max_digits=12),
                ),
                ("runtime_seconds", models.PositiveIntegerField(default=0)),
                ("usage_date", models.DateField(default=django.utils.timezone.localdate)),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cloud_usage_entries",
                        to="monitoring.pipelinejob",
                    ),
                ),
                (
                    "profile",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="cloud_usage_entries",
                        to="monitoring.computeprofileconfig",
                    ),
                ),
            ],
            options={
                "ordering": ["-usage_date", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["provider", "usage_date"],
                        name="dash_usage_provider_idx",
                    ),
                    models.Index(
                        fields=["profile", "usage_date"],
                        name="dash_usage_profile_idx",
                    ),
                    models.Index(
                        fields=["job", "usage_date"],
                        name="dash_usage_job_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="JobRunEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("queued", "Queued"),
                            ("started", "Started"),
                            ("progress", "Progress"),
                            ("stdout", "Stdout"),
                            ("stderr", "Stderr"),
                            ("warning", "Warning"),
                            ("failed", "Failed"),
                            ("succeeded", "Succeeded"),
                            ("cancelled", "Cancelled"),
                            ("budget_blocked", "Budget blocked"),
                            ("approval_required", "Approval required"),
                            ("resource_blocked", "Resource blocked"),
                        ],
                        max_length=32,
                    ),
                ),
                ("message", models.TextField(blank=True)),
                ("payload_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="run_events",
                        to="monitoring.pipelinejob",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["job", "created_at"],
                        name="dash_event_job_idx",
                    ),
                    models.Index(
                        fields=["event_type", "created_at"],
                        name="dash_event_type_idx",
                    ),
                ],
            },
        ),
    ]
