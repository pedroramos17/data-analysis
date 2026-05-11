"""Add dashboard export artifacts and NLP run metrics."""

from django.db import migrations, models


class Migration(migrations.Migration):
    """Create operational models for dashboard-run jobs."""

    dependencies = [
        ("monitoring", "0003_alertrule_canonicalurl_discoverycandidate_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExportArtifact",
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
                ("export_type", models.CharField(default="documents", max_length=80)),
                ("path", models.CharField(max_length=1200, unique=True)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("byte_size", models.PositiveBigIntegerField(default=0)),
                ("schema", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["export_type", "created_at"],
                        name="monitoring__export__cbb65e_idx",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="NlpRunMetric",
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
                ("entrypoint", models.CharField(max_length=80)),
                ("tasks", models.JSONField(blank=True, default=list)),
                ("text_hash", models.CharField(max_length=64)),
                ("text_length", models.PositiveIntegerField(default=0)),
                ("token_count", models.PositiveIntegerField(default=0)),
                ("total_ms", models.FloatField(default=0)),
                ("task_costs", models.JSONField(blank=True, default=dict)),
                ("model_versions", models.JSONField(blank=True, default=dict)),
                ("success", models.BooleanField(default=True)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["entrypoint", "created_at"],
                        name="monitoring__entrypo_829944_idx",
                    )
                ],
            },
        ),
    ]
