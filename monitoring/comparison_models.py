"""Article enrichment, event comparison, and review models."""

from django.db import models
from django.utils import timezone


class ArticleEntityMention(models.Model):
    """A normalized entity mention in one article.

    Example:
        `ArticleEntityMention.objects.filter(article=article)`
    """

    article = models.ForeignKey(
        "monitoring.NormalizedDocument", on_delete=models.CASCADE
    )
    entity = models.ForeignKey("monitoring.CanonicalEntity", on_delete=models.CASCADE)
    mention_text = models.CharField(max_length=240)
    mention_count = models.PositiveIntegerField(default=1)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    backend = models.CharField(max_length=80, default="local_heuristic")
    context = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["article_id", "entity__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "entity", "backend"],
                name="unique_article_entity_backend",
            )
        ]

    def __str__(self) -> str:
        """Return a compact mention label.

        Example:
            `str(mention)`
        """
        return f"{self.article_id}:{self.entity_id}"


class ArticleEmbedding(models.Model):
    """A pluggable embedding vector for an article.

    Example:
        `ArticleEmbedding.objects.get(article=article, backend="local_hash")`
    """

    article = models.ForeignKey(
        "monitoring.NormalizedDocument", on_delete=models.CASCADE
    )
    backend = models.CharField(max_length=80)
    model_name = models.CharField(max_length=160, blank=True)
    vector = models.JSONField(default=list, blank=True)
    dimensions = models.PositiveIntegerField(default=0)
    text_hash = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["article_id", "backend"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "backend"],
                name="unique_article_embedding_backend",
            )
        ]

    def __str__(self) -> str:
        """Return a compact embedding label.

        Example:
            `str(embedding)`
        """
        return f"{self.article_id}:{self.backend}"


class Claim(models.Model):
    """A claim candidate extracted from an article.

    Example:
        `Claim.objects.filter(article=article)`
    """

    article = models.ForeignKey(
        "monitoring.NormalizedDocument", on_delete=models.CASCADE
    )
    claim_text = models.TextField()
    normalized_claim = models.CharField(max_length=500)
    claim_type = models.CharField(max_length=80, default="statement")
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    backend = models.CharField(max_length=80, default="local_heuristic")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["article_id", "id"]
        indexes = [models.Index(fields=["normalized_claim"])]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "normalized_claim", "backend"],
                name="unique_article_claim_backend",
            )
        ]

    def __str__(self) -> str:
        """Return a compact claim preview.

        Example:
            `str(claim)`
        """
        return self.claim_text[:120]


class FrameFeature(models.Model):
    """An explainable framing feature measured for one article.

    Example:
        `FrameFeature.objects.filter(article=article, feature_type="quote_density")`
    """

    article = models.ForeignKey(
        "monitoring.NormalizedDocument", on_delete=models.CASCADE
    )
    feature_type = models.CharField(max_length=80)
    value = models.FloatField(default=0)
    evidence = models.JSONField(default=dict, blank=True)
    backend = models.CharField(max_length=80, default="local_heuristic")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["article_id", "feature_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["article", "feature_type", "backend"],
                name="unique_article_frame_feature",
            )
        ]

    def __str__(self) -> str:
        """Return the frame feature label.

        Example:
            `str(feature)`
        """
        return f"{self.article_id}:{self.feature_type}"


class EventCoverage(models.Model):
    """Coverage counts for one event at source, provider, or owner level.

    Example:
        `EventCoverage.objects.filter(event=event, coverage_type="provider")`
    """

    event = models.ForeignKey("monitoring.TopicCluster", on_delete=models.CASCADE)
    coverage_type = models.CharField(max_length=20)
    source = models.ForeignKey(
        "monitoring.Source", null=True, blank=True, on_delete=models.CASCADE
    )
    provider = models.ForeignKey(
        "monitoring.Provider", null=True, blank=True, on_delete=models.CASCADE
    )
    owner = models.ForeignKey(
        "monitoring.Owner", null=True, blank=True, on_delete=models.CASCADE
    )
    article_count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    dominant_entities = models.JSONField(default=list, blank=True)
    shared_claims = models.JSONField(default=list, blank=True)
    unique_claims = models.JSONField(default=list, blank=True)
    omissions = models.JSONField(default=list, blank=True)
    framing = models.JSONField(default=dict, blank=True)
    amplification_score = models.FloatField(default=1)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_id", "coverage_type"]
        indexes = [
            models.Index(fields=["event", "coverage_type"]),
            models.Index(fields=["provider"]),
            models.Index(fields=["owner"]),
        ]

    def __str__(self) -> str:
        """Return the coverage row label.

        Example:
            `str(coverage)`
        """
        return f"{self.event_id}:{self.coverage_type}:{self.article_count}"


class ClaimCluster(models.Model):
    """A normalized claim group within one event.

    Example:
        `ClaimCluster.objects.filter(event=event)`
    """

    event = models.ForeignKey("monitoring.TopicCluster", on_delete=models.CASCADE)
    normalized_claim = models.CharField(max_length=500)
    representative_claim = models.TextField()
    provider_count = models.PositiveIntegerField(default=0)
    article_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event_id", "representative_claim"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "normalized_claim"],
                name="unique_event_claim_cluster",
            )
        ]

    def __str__(self) -> str:
        """Return the representative claim preview.

        Example:
            `str(cluster)`
        """
        return self.representative_claim[:120]


class ClaimClusterMember(models.Model):
    """A claim-to-cluster membership edge.

    Example:
        `ClaimClusterMember.objects.filter(claim_cluster=cluster)`
    """

    claim_cluster = models.ForeignKey(ClaimCluster, on_delete=models.CASCADE)
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE)
    similarity = models.FloatField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["claim_cluster_id", "claim_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["claim_cluster", "claim"],
                name="unique_claim_cluster_member",
            )
        ]

    def __str__(self) -> str:
        """Return the cluster-member label.

        Example:
            `str(member)`
        """
        return f"{self.claim_cluster_id}:{self.claim_id}"


class EventComparisonSnapshot(models.Model):
    """A materialized neutral comparison snapshot for an event.

    Example:
        `EventComparisonSnapshot.objects.filter(event=event).latest("generated_at")`
    """

    event = models.ForeignKey("monitoring.TopicCluster", on_delete=models.CASCADE)
    generated_at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict, blank=True)
    snapshot_hash = models.CharField(max_length=64)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-generated_at"]
        indexes = [models.Index(fields=["event", "generated_at"])]

    def __str__(self) -> str:
        """Return the snapshot label.

        Example:
            `str(snapshot)`
        """
        return f"{self.event_id}:{self.generated_at.isoformat()}"
