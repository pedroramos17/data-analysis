# Generated manually because this environment does not have Django installed.

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0008_dashboard_operational_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResourceLock",
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
                ("resource_name", models.CharField(max_length=120, unique=True)),
                ("locked_by_worker", models.CharField(max_length=150)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "heartbeat_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resource_locks",
                        to="monitoring.pipelinejob",
                    ),
                ),
            ],
            options={
                "ordering": ["resource_name"],
                "indexes": [
                    models.Index(fields=["expires_at"], name="orch_lock_expires_idx"),
                    models.Index(
                        fields=["locked_by_worker"],
                        name="orch_lock_worker_idx",
                    ),
                    models.Index(fields=["job"], name="orch_lock_job_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="WorkerHeartbeat",
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
                ("worker_id", models.CharField(max_length=150, unique=True)),
                ("hostname", models.CharField(max_length=255)),
                ("profile", models.CharField(max_length=40)),
                ("backend", models.CharField(default="auto", max_length=20)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("starting", "Starting"),
                            ("idle", "Idle"),
                            ("running", "Running"),
                            ("stopped", "Stopped"),
                            ("error", "Error"),
                            ("stale", "Stale"),
                        ],
                        default="starting",
                        max_length=32,
                    ),
                ),
                ("pid", models.PositiveIntegerField(default=0)),
                (
                    "started_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "last_heartbeat_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("metadata_json", models.JSONField(blank=True, default=dict)),
                (
                    "current_job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="worker_heartbeats",
                        to="monitoring.pipelinejob",
                    ),
                ),
            ],
            options={
                "ordering": ["worker_id"],
                "indexes": [
                    models.Index(
                        fields=["profile", "status"],
                        name="orch_worker_profile_idx",
                    ),
                    models.Index(
                        fields=["last_heartbeat_at"],
                        name="orch_worker_heartbeat_idx",
                    ),
                    models.Index(
                        fields=["current_job"],
                        name="orch_worker_job_idx",
                    ),
                ],
            },
        ),
    ]
