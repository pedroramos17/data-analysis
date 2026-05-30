"""SQLite metadata models for the Quant4 research platform."""

from __future__ import annotations

from django.db import models


class ReproducibleRecord(models.Model):
    """Shared metadata required for local research reproducibility.

    Example:
        `WindowArtifact.objects.values("config_hash", "random_seed")`
    """

    config_json = models.JSONField(default=dict, blank=True)
    config_hash = models.CharField(max_length=64)
    random_seed = models.IntegerField(default=0)
    data_start = models.DateField(null=True, blank=True)
    data_end = models.DateField(null=True, blank=True)
    split_start = models.DateField(null=True, blank=True)
    split_end = models.DateField(null=True, blank=True)
    provenance_json = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True


class TimestampedRecord(models.Model):
    """Shared creation timestamps for registry metadata.

    Example:
        `Asset.objects.order_by("-created_at")`
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Asset(TimestampedRecord):
    """A locally registered research asset.

    Example:
        `Asset.objects.get(symbol="SPY")`
    """

    symbol = models.CharField(max_length=64)
    asset_type = models.CharField(max_length=40, default="equity")
    name = models.CharField(max_length=180, blank=True)
    exchange = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=12, default="USD")
    is_active = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    provenance_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["symbol", "asset_type", "exchange"]
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "asset_type", "exchange"],
                name="uniq_quant4_asset_identity",
            )
        ]
        indexes = [models.Index(fields=["symbol", "asset_type"])]

    def __str__(self) -> str:
        """Return the asset symbol used in lists."""
        return self.symbol


class MarketDataset(TimestampedRecord):
    """Metadata for a local market dataset.

    Example:
        `MarketDataset.objects.filter(frequency="1d")`
    """

    asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="datasets",
    )
    name = models.CharField(max_length=180)
    source = models.CharField(max_length=120)
    frequency = models.CharField(max_length=40)
    data_start = models.DateField(null=True, blank=True)
    data_end = models.DateField(null=True, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    metadata_json = models.JSONField(default=dict, blank=True)
    provenance_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "source"],
                name="uniq_quant4_market_dataset",
            )
        ]

    def __str__(self) -> str:
        """Return the dataset name."""
        return self.name


class Experiment(ReproducibleRecord, TimestampedRecord):
    """A reproducible Quant4 experiment envelope.

    Example:
        `Experiment.objects.create(name="baseline", config_hash="...")`
    """

    name = models.CharField(max_length=180, unique=True)
    component_name = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=40, default="DRAFT")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the experiment name."""
        return self.name


class WindowArtifact(ReproducibleRecord, TimestampedRecord):
    """Metadata for leakage-safe train/validation/test windows.

    Example:
        `WindowArtifact.objects.filter(dataset=dataset)`
    """

    experiment = models.ForeignKey(
        Experiment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="window_artifacts",
    )
    dataset = models.ForeignKey(
        MarketDataset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="window_artifacts",
    )
    name = models.CharField(max_length=180)
    artifact_uri = models.CharField(max_length=1200, blank=True)
    split_metadata_json = models.JSONField(default=dict, blank=True)
    feature_schema_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the artifact name."""
        return self.name


class FeatureArtifact(ReproducibleRecord, TimestampedRecord):
    """Metadata for materialized feature matrices.

    Example:
        `FeatureArtifact.objects.filter(feature_set_name="returns")`
    """

    dataset = models.ForeignKey(
        MarketDataset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feature_artifacts",
    )
    feature_set_name = models.CharField(max_length=180)
    artifact_uri = models.CharField(max_length=1200, blank=True)
    feature_schema_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the feature set name."""
        return self.feature_set_name


class Quant4RunRecord(ReproducibleRecord, TimestampedRecord):
    """Shared fields for Quant4 research runs.

    Example:
        `ModelRun.objects.filter(status="PLANNED")`
    """

    experiment = models.ForeignKey(
        Experiment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_records",
    )
    name = models.CharField(max_length=180)
    component_name = models.CharField(max_length=120)
    status = models.CharField(max_length=40, default="PLANNED")
    metrics_json = models.JSONField(default=dict, blank=True)
    artifact_uri = models.CharField(max_length=1200, blank=True)
    feature_schema_json = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the run name."""
        return self.name


class RegimeRun(Quant4RunRecord):
    """A regime detector run."""


class RiskRun(Quant4RunRecord):
    """A risk model run."""


class LOBRun(Quant4RunRecord):
    """A limit-order-book research run."""


class GraphSnapshot(Quant4RunRecord):
    """A graph builder output snapshot."""

    node_count = models.PositiveIntegerField(default=0)
    edge_count = models.PositiveIntegerField(default=0)


class PortfolioRun(Quant4RunRecord):
    """A portfolio optimizer research run."""


class ModelRun(Quant4RunRecord):
    """A registered model run."""


class BacktestRun(Quant4RunRecord):
    """A backtest simulation run."""


class ExplainabilityReport(Quant4RunRecord):
    """A model-risk and explainability report."""

    report_json = models.JSONField(default=dict, blank=True)
