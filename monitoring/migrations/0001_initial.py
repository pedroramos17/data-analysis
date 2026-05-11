# Generated for the initial public source monitor scaffold.

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    """Create monitoring source, raw, normalized, job, and review tables."""

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Source",
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
                ("name", models.CharField(max_length=180, unique=True)),
                ("url", models.URLField(max_length=1200)),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("rss", "RSS"),
                            ("sitemap", "Sitemap"),
                            ("html", "HTML"),
                            ("api", "API"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "fetch_method",
                    models.CharField(
                        choices=[
                            ("http", "HTTP"),
                            ("browser", "Headless browser"),
                            ("api", "Approved API"),
                        ],
                        max_length=20,
                    ),
                ),
                ("cadence_minutes", models.PositiveIntegerField(default=60)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("is_enabled", models.BooleanField(default=True)),
                ("rate_limit_seconds", models.PositiveIntegerField(default=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="FetchJob",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                        ],
                        max_length=20,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
                ("metrics", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.source",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="IngestionCheckpoint",
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
                ("cursor", models.CharField(blank=True, max_length=1200)),
                ("last_success_at", models.DateTimeField(blank=True, null=True)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("last_status", models.CharField(blank=True, max_length=32)),
                ("item_count", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                (
                    "source",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.source",
                    ),
                ),
            ],
            options={
                "ordering": ["source__name"],
            },
        ),
        migrations.CreateModel(
            name="RawEvent",
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
                ("url", models.URLField(max_length=1200)),
                ("external_id", models.CharField(blank=True, max_length=512)),
                ("content_hash", models.CharField(max_length=64)),
                ("payload_text", models.TextField()),
                ("http_status", models.PositiveIntegerField(default=200)),
                ("headers", models.JSONField(blank=True, default=dict)),
                ("fetched_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("snapshot_path", models.CharField(blank=True, max_length=1200)),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.source",
                    ),
                ),
            ],
            options={
                "ordering": ["-fetched_at"],
            },
        ),
        migrations.CreateModel(
            name="DeadLetter",
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
                ("url", models.URLField(max_length=1200)),
                ("reason", models.TextField()),
                ("payload_excerpt", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "raw_event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="monitoring.rawevent",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.source",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="NormalizedDocument",
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
                ("canonical_url", models.URLField(max_length=1200)),
                ("title", models.CharField(max_length=500)),
                ("author", models.CharField(blank=True, max_length=300)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("language", models.CharField(blank=True, max_length=16)),
                ("content", models.TextField(blank=True)),
                ("entities", models.JSONField(blank=True, default=list)),
                ("tags", models.JSONField(blank=True, default=list)),
                ("dedupe_hash", models.CharField(max_length=64, unique=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "raw_event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.rawevent",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="monitoring.source",
                    ),
                ),
            ],
            options={
                "ordering": ["-published_at", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="source",
            index=models.Index(
                fields=["is_enabled", "source_type"],
                name="monitoring__is_enab_0faf7f_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="source",
            index=models.Index(
                fields=["fetch_method"], name="monitoring__fetch_m_983ea6_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="fetchjob",
            index=models.Index(
                fields=["source", "status"], name="monitoring__source__a93eb6_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="fetchjob",
            index=models.Index(
                fields=["created_at"], name="monitoring__created_18e54b_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="rawevent",
            index=models.Index(
                fields=["source", "fetched_at"], name="monitoring__source__416fd0_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="rawevent",
            index=models.Index(
                fields=["content_hash"], name="monitoring__content_05de89_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="rawevent",
            constraint=models.UniqueConstraint(
                fields=("source", "content_hash"), name="unique_raw_event_source_hash"
            ),
        ),
        migrations.AddIndex(
            model_name="deadletter",
            index=models.Index(
                fields=["source", "created_at"], name="monitoring__source__c794d1_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="deadletter",
            index=models.Index(
                fields=["resolved_at"], name="monitoring__resolve_b743ef_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="normalizeddocument",
            index=models.Index(
                fields=["source", "published_at"], name="monitoring__source__147aab_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="normalizeddocument",
            index=models.Index(
                fields=["dedupe_hash"], name="monitoring__dedupe__188616_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="normalizeddocument",
            index=models.Index(
                fields=["language"], name="monitoring__languag_6b8451_idx"
            ),
        ),
    ]
