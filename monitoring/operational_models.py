"""Small operational models for exports and local NLP metrics."""

from django.db import models


class ExportArtifact(models.Model):
    """A Parquet export artifact available for review."""

    export_type = models.CharField(max_length=80, default="documents")
    path = models.CharField(max_length=1200, unique=True)
    row_count = models.PositiveIntegerField(default=0)
    byte_size = models.PositiveBigIntegerField(default=0)
    schema = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["export_type", "created_at"])]

    def __str__(self) -> str:
        """Return the artifact path."""
        return self.path


class NlpRunMetric(models.Model):
    """CPU-first NLP pipeline timing and model metadata."""

    entrypoint = models.CharField(max_length=80)
    tasks = models.JSONField(default=list, blank=True)
    text_hash = models.CharField(max_length=64)
    text_length = models.PositiveIntegerField(default=0)
    token_count = models.PositiveIntegerField(default=0)
    total_ms = models.FloatField(default=0)
    task_costs = models.JSONField(default=dict, blank=True)
    model_versions = models.JSONField(default=dict, blank=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["entrypoint", "created_at"])]

    def __str__(self) -> str:
        """Return a compact metric label."""
        return f"{self.entrypoint}:{self.total_ms:.2f}ms"
