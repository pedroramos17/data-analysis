"""Phase 2 intelligence models for discovery, alerts, and enrichment."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from monitoring.models import NormalizedDocument, Source


class DocumentEnrichment(models.Model):
    """Local NLP and data-quality metadata for one document."""

    document = models.OneToOneField(NormalizedDocument, on_delete=models.CASCADE)
    detected_language = models.CharField(max_length=16, blank=True)
    summary = models.TextField(blank=True)
    keywords = models.JSONField(default=list, blank=True)
    hashtags = models.JSONField(default=list, blank=True)
    sentiment_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    quality_flags = models.JSONField(default=list, blank=True)
    enrichment_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["detected_language"])]

    def __str__(self) -> str:
        """Return the enrichment label used by admin."""
        return f"enrichment:{self.document_id}"


class DiscoveryCandidate(models.Model):
    """A candidate source discovered from existing public content."""

    class CandidateType(models.TextChoices):
        RSS = "rss", "RSS"
        DOMAIN = "domain", "Domain"
        TOPIC = "topic", "Topic"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    candidate_type = models.CharField(max_length=20, choices=CandidateType.choices)
    name = models.CharField(max_length=240)
    url = models.URLField(max_length=1200)
    evidence_url = models.URLField(max_length=1200, blank=True)
    confidence = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    category = models.CharField(max_length=32, choices=Source.Category.choices)
    tags = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-confidence", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate_type", "url"],
                name="unique_discovery_candidate",
            )
        ]

    def __str__(self) -> str:
        """Return the candidate name shown in admin."""
        return self.name


class AlertRule(models.Model):
    """An in-app alert rule evaluated against enriched documents."""

    class RuleType(models.TextChoices):
        KEYWORD = "keyword", "Keyword"
        ENTITY = "entity", "Entity"
        CATEGORY = "category", "Category"
        VOLUME = "volume", "Volume"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    name = models.CharField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    rule_type = models.CharField(max_length=20, choices=RuleType.choices)
    query = models.CharField(max_length=240, blank=True)
    entity_filters = models.JSONField(default=list, blank=True)
    topic_filters = models.JSONField(default=list, blank=True)
    source_filters = models.JSONField(default=list, blank=True)
    min_severity = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    min_novelty = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    min_trend = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    category = models.CharField(
        max_length=32, choices=Source.Category.choices, blank=True
    )
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.MEDIUM
    )
    is_enabled = models.BooleanField(default=True)
    enabled = models.BooleanField(default=True)
    cooldown_minutes = models.PositiveIntegerField(default=60)
    threshold_count = models.PositiveIntegerField(default=1)
    lookback_minutes = models.PositiveIntegerField(default=1440)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["rule_type", "is_enabled"])]

    def __str__(self) -> str:
        """Return the alert rule name."""
        return self.name


class AlertDetector(models.Model):
    """Automatic detector configuration for cluster-level alert signals."""

    class DetectorType(models.TextChoices):
        EMERGING_TOPIC = "emerging_topic", "Emerging topic"
        ANOMALY = "anomaly", "Anomaly"
        ENTITY_BURST = "entity_burst", "Entity burst"
        SOURCE_BURST = "source_burst", "Source burst"
        MARKET_SHOCK = "market_shock", "Market shock"
        CONTRADICTION = "contradiction", "Contradiction"

    name = models.CharField(max_length=180, unique=True)
    detector_type = models.CharField(max_length=40, choices=DetectorType.choices)
    config = models.JSONField(default=dict, blank=True)
    sensitivity = models.DecimalField(max_digits=4, decimal_places=2, default=0.5)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["detector_type", "enabled"])]

    def __str__(self) -> str:
        """Return the detector name."""
        return self.name


class AlertHit(models.Model):
    """A materialized signal produced by rules or automatic detectors."""

    class TriggerType(models.TextChoices):
        EXPLICIT_RULE_MATCH = "explicit_rule_match", "Explicit rule match"
        AUTOMATIC_CLUSTER = "automatic_emerging_cluster", "Automatic cluster"
        ANOMALY = "anomaly", "Anomaly"
        ENTITY_BURST = "entity_burst", "Entity burst"
        MARKET_SHOCK = "market_shock", "Market shock"
        CONTRADICTION = "contradiction", "Contradiction"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"
        IGNORED = "ignored", "Ignored"
        DUPLICATE = "duplicate", "Duplicate"

    rule = models.ForeignKey(
        AlertRule, null=True, blank=True, on_delete=models.SET_NULL
    )
    detector = models.ForeignKey(
        AlertDetector, null=True, blank=True, on_delete=models.SET_NULL
    )
    cluster = models.ForeignKey(
        "TopicCluster", null=True, blank=True, on_delete=models.CASCADE
    )
    representative_document = models.ForeignKey(
        NormalizedDocument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="representative_alerts",
    )
    document = models.ForeignKey(
        NormalizedDocument, null=True, blank=True, on_delete=models.SET_NULL
    )
    source = models.ForeignKey(Source, null=True, blank=True, on_delete=models.SET_NULL)
    dedupe_hash = models.CharField(max_length=64, unique=True)
    dedupe_key = models.CharField(max_length=128, unique=True, null=True, blank=True)
    trigger_type = models.CharField(
        max_length=40,
        choices=TriggerType.choices,
        default=TriggerType.EXPLICIT_RULE_MATCH,
    )
    title = models.CharField(max_length=500)
    matched_text = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=AlertRule.Severity.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    severity_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    novelty_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    trend_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    source_diversity_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    entity_importance_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    market_relevance_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    detected_at = models.DateTimeField(default=timezone.now)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["severity", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(rule__isnull=False) | Q(detector__isnull=False),
                name="alert_hit_rule_or_detector",
            )
        ]

    def __str__(self) -> str:
        """Return the alert hit title."""
        return self.title

    def clean(self) -> None:
        """Require either an explicit rule or automatic detector."""
        if self.rule_id or self.detector_id:
            return
        raise ValidationError("Invalid alert hit trigger; expected rule or detector")


class TopicCluster(models.Model):
    """An event cluster joining evidence about the same story."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        STALE = "stale", "Stale"
        MERGED = "merged", "Merged"
        IGNORED = "ignored", "Ignored"

    label = models.CharField(max_length=240)
    canonical_title = models.CharField(max_length=500, blank=True)
    summary = models.TextField(blank=True)
    topic_label = models.CharField(max_length=240, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    keywords = models.JSONField(default=list, blank=True)
    entities = models.JSONField(default=list, blank=True)
    document_count = models.PositiveIntegerField(default=0)
    source_count = models.PositiveIntegerField(default=0)
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    novelty_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    trend_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    severity_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    metadata = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["label", "window_start"], name="unique_topic_cluster"
            )
        ]

    def __str__(self) -> str:
        """Return the topic cluster label."""
        return self.label


class DocumentTopic(models.Model):
    """Evidence membership edge between a document and event cluster."""

    class Role(models.TextChoices):
        REPRESENTATIVE = "representative", "Representative"
        EVIDENCE = "evidence", "Evidence"
        DUPLICATE = "duplicate", "Duplicate"
        CONTRADICTION = "contradiction", "Contradiction"
        SOURCE_OF_CLAIM = "source_of_claim", "Source of claim"

    cluster = models.ForeignKey(TopicCluster, on_delete=models.CASCADE)
    document = models.ForeignKey(NormalizedDocument, on_delete=models.CASCADE)
    overlap_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    similarity = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    role = models.CharField(max_length=40, choices=Role.choices, default=Role.EVIDENCE)

    class Meta:
        ordering = ["cluster_id", "-overlap_score"]
        constraints = [
            models.UniqueConstraint(
                fields=["cluster", "document"], name="unique_document_topic"
            )
        ]

    def __str__(self) -> str:
        """Return the document-topic edge label."""
        return f"{self.cluster_id}:{self.document_id}"


class DedupeGroup(models.Model):
    """Exact, near, or semantic duplicate group for documents."""

    class GroupType(models.TextChoices):
        EXACT = "exact", "Exact"
        NEAR = "near", "Near"
        SEMANTIC = "semantic", "Semantic"

    group_type = models.CharField(max_length=20, choices=GroupType.choices)
    content_hash = models.CharField(max_length=64, null=True, blank=True)
    simhash = models.CharField(max_length=64, null=True, blank=True)
    representative_document = models.ForeignKey(
        NormalizedDocument, null=True, blank=True, on_delete=models.SET_NULL
    )
    document_count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["group_type", "content_hash"]),
            models.Index(fields=["group_type", "simhash"]),
        ]

    def __str__(self) -> str:
        """Return the dedupe group label."""
        return f"{self.group_type}:{self.document_count}"


class AlertHitDocument(models.Model):
    """Evidence mapping between an alert and its documents."""

    alert_hit = models.ForeignKey(AlertHit, on_delete=models.CASCADE)
    document = models.ForeignKey(NormalizedDocument, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=40,
        choices=DocumentTopic.Role.choices,
        default=DocumentTopic.Role.EVIDENCE,
    )
    similarity_to_cluster = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    source_reliability_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    matched_text = models.TextField(blank=True)

    class Meta:
        ordering = ["alert_hit_id", "role"]
        constraints = [
            models.UniqueConstraint(
                fields=["alert_hit", "document"], name="unique_alert_hit_document"
            )
        ]

    def __str__(self) -> str:
        """Return the alert-document edge label."""
        return f"{self.alert_hit_id}:{self.document_id}"


class AlertFeedback(models.Model):
    """Human-in-loop feedback for future alert ranking."""

    class Label(models.TextChoices):
        USEFUL = "useful", "Useful"
        FALSE_POSITIVE = "false_positive", "False positive"
        DUPLICATE = "duplicate", "Duplicate"
        TOO_LATE = "too_late", "Too late"
        TOO_LOW_SEVERITY = "too_low_severity", "Too low severity"
        TOO_HIGH_SEVERITY = "too_high_severity", "Too high severity"

    alert_hit = models.ForeignKey(AlertHit, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    label = models.CharField(max_length=40, choices=Label.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["label", "created_at"])]

    def __str__(self) -> str:
        """Return the feedback label."""
        return self.label


class SourceReputationSnapshot(models.Model):
    """A computed reputation score snapshot for a source."""

    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    score = models.DecimalField(max_digits=4, decimal_places=2)
    components = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-window_end", "source__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "window_start", "window_end"],
                name="unique_reputation_snapshot",
            )
        ]

    def __str__(self) -> str:
        """Return the reputation snapshot label."""
        return f"{self.source_id}:{self.score}"


class CanonicalUrl(models.Model):
    """A canonical URL reference shared by documents."""

    canonical_url = models.URLField(max_length=1200, unique=True)
    domain = models.CharField(max_length=240)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["domain", "canonical_url"]
        indexes = [models.Index(fields=["domain"])]

    def __str__(self) -> str:
        """Return the canonical URL."""
        return self.canonical_url


class DocumentUrlReference(models.Model):
    """A document-to-canonical-URL reference edge."""

    document = models.ForeignKey(NormalizedDocument, on_delete=models.CASCADE)
    canonical_url = models.ForeignKey(CanonicalUrl, on_delete=models.CASCADE)
    reference_type = models.CharField(max_length=80, default="canonical")

    class Meta:
        ordering = ["document_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "canonical_url", "reference_type"],
                name="unique_document_url_reference",
            )
        ]

    def __str__(self) -> str:
        """Return the URL reference label."""
        return f"{self.document_id}:{self.canonical_url_id}"
