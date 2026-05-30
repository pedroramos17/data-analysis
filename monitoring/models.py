"""SQLite-backed operational models for public-source ingestion."""

from django.db import models
from django.utils import timezone


class Source(models.Model):
    """A public source that can be fetched on a schedule.

    Example:
        `Source.objects.create(name="CISA", source_type=Source.SourceType.RSS)`
    """

    class SourceType(models.TextChoices):
        RSS = "rss", "RSS"
        SITEMAP = "sitemap", "Sitemap"
        HTML = "html", "HTML"
        API = "api", "API"

    class SourceKind(models.TextChoices):
        RSS = "rss", "RSS"
        NEWS = "news", "News"
        GOV = "gov", "Government"
        PAPER = "paper", "Paper"
        SOCIAL = "social", "Social"
        OTHER = "other", "Other"

    class FetchMethod(models.TextChoices):
        HTTP = "http", "HTTP"
        BROWSER = "browser", "Headless browser"
        API = "api", "Approved API"

    class Category(models.TextChoices):
        WORLD = "world", "World"
        POLITICS = "politics", "Politics"
        BUSINESS = "business", "Business"
        MARKETS = "markets", "Markets"
        TECHNOLOGY = "technology", "Technology"
        SECURITY = "security", "Security"
        DEFENSE = "defense", "Defense"
        SCIENCE = "science", "Science"
        HEALTH = "health", "Health"
        ENERGY = "energy", "Energy"
        CLIMATE = "climate", "Climate"
        LEGAL = "legal", "Legal"
        POLICY = "policy", "Policy"
        CULTURE = "culture", "Culture"
        REGIONAL = "regional", "Regional"

    name = models.CharField(max_length=180, unique=True)
    url = models.URLField(max_length=1200)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    fetch_method = models.CharField(max_length=20, choices=FetchMethod.choices)
    cadence_minutes = models.PositiveIntegerField(default=60)
    tags = models.JSONField(default=list, blank=True)
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        default=Category.WORLD,
    )
    language = models.CharField(max_length=16, default="en")
    country = models.CharField(max_length=80, blank=True)
    source_kind = models.CharField(
        max_length=20,
        choices=SourceKind.choices,
        default=SourceKind.NEWS,
    )
    source_tier = models.PositiveSmallIntegerField(default=3)
    reputation_score = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    reliability_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    state_affiliation = models.CharField(max_length=180, blank=True)
    propaganda_risk = models.BooleanField(default=False)
    is_dynamic = models.BooleanField(default=False)
    query_template = models.CharField(max_length=1200, blank=True)
    is_enabled = models.BooleanField(default=True)
    rate_limit_seconds = models.PositiveIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_enabled", "source_type"]),
            models.Index(fields=["fetch_method"]),
            models.Index(fields=["category", "source_tier"]),
        ]

    def __str__(self) -> str:
        """Return the display name used by the admin.

        Example:
            `str(source)`
        """
        return self.name


class RawEvent(models.Model):
    """A raw fetched payload before normalization.

    Example:
        `RawEvent.objects.filter(source=source).latest("fetched_at")`
    """

    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    url = models.URLField(max_length=1200)
    external_id = models.CharField(max_length=512, blank=True)
    content_hash = models.CharField(max_length=64)
    payload_text = models.TextField()
    http_status = models.PositiveIntegerField(default=200)
    headers = models.JSONField(default=dict, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    snapshot_path = models.CharField(max_length=1200, blank=True)

    class Meta:
        ordering = ["-fetched_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "content_hash"],
                name="unique_raw_event_source_hash",
            )
        ]
        indexes = [
            models.Index(fields=["source", "fetched_at"]),
            models.Index(fields=["content_hash"]),
        ]

    def __str__(self) -> str:
        """Return a compact raw event label.

        Example:
            `str(raw_event)`
        """
        return f"{self.source_id}:{self.content_hash[:12]}"


class NormalizedDocument(models.Model):
    """A normalized document ready for search, review, and export.

    Example:
        `NormalizedDocument.objects.filter(language="en")`
    """

    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    raw_event = models.OneToOneField(RawEvent, on_delete=models.CASCADE)
    canonical_url = models.URLField(max_length=1200)
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=300, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=16, blank=True)
    content = models.TextField(blank=True)
    text = models.TextField(blank=True)
    entities = models.JSONField(default=list, blank=True)
    tags = models.JSONField(default=list, blank=True)
    dedupe_hash = models.CharField(max_length=64, unique=True)
    content_hash = models.CharField(max_length=64, blank=True)
    simhash = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ingested_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        indexes = [
            models.Index(fields=["source", "published_at"]),
            models.Index(fields=["dedupe_hash"]),
            models.Index(fields=["content_hash"]),
            models.Index(fields=["simhash"]),
            models.Index(fields=["language"]),
            models.Index(fields=["published_at"]),
            models.Index(fields=["ingested_at"]),
        ]

    def __str__(self) -> str:
        """Return the title shown in review lists.

        Example:
            `str(document)`
        """
        return self.title


class IngestionCheckpoint(models.Model):
    """Replay cursor and last outcome for a source.

    Example:
        `IngestionCheckpoint.objects.get(source=source).last_status`
    """

    source = models.OneToOneField(Source, on_delete=models.CASCADE)
    cursor = models.CharField(max_length=1200, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=32, blank=True)
    item_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    cooldown_until = models.DateTimeField(null=True, blank=True)
    last_http_status = models.PositiveIntegerField(null=True, blank=True)
    last_error_type = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["source__name"]

    def __str__(self) -> str:
        """Return the source checkpoint label.

        Example:
            `str(checkpoint)`
        """
        return f"{self.source_id}:{self.last_status or 'never'}"


class DigestCache(models.Model):
    """SQLite-backed cache for digest API payloads.

    Example:
        `DigestCache.objects.get(cache_key="feed-digest")`
    """

    cache_key = models.CharField(max_length=120, unique=True)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["cache_key"]
        indexes = [
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        """Return the cache key shown in admin.

        Example:
            `str(cache_entry)`
        """
        return self.cache_key


class FetchJob(models.Model):
    """A bounded fetch attempt for tracking retries and failures.

    Example:
        `FetchJob.objects.filter(status=FetchJob.Status.FAILED)`
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices)
    attempts = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        """Return a concise job label.

        Example:
            `str(fetch_job)`
        """
        return f"{self.source_id}:{self.status}:{self.attempts}"


class DeadLetter(models.Model):
    """A failed page or record preserved for review.

    Example:
        `DeadLetter.objects.filter(resolved_at__isnull=True)`
    """

    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    raw_event = models.ForeignKey(
        RawEvent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    url = models.URLField(max_length=1200)
    reason = models.TextField()
    payload_excerpt = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "created_at"]),
            models.Index(fields=["resolved_at"]),
        ]

    def __str__(self) -> str:
        """Return the unresolved review label.

        Example:
            `str(dead_letter)`
        """
        return f"{self.source_id}:{self.url}"


class CanonicalEntity(models.Model):
    """A resolved entity mentioned by normalized documents.

    Example:
        `CanonicalEntity.objects.filter(entity_type="organization")`
    """

    name = models.CharField(max_length=240, unique=True)
    normalized_name = models.CharField(max_length=240, unique=True)
    entity_type = models.CharField(max_length=80, default="unknown")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["entity_type"]),
        ]

    def __str__(self) -> str:
        """Return the canonical entity name.

        Example:
            `str(entity)`
        """
        return self.name


class EntityAlias(models.Model):
    """An alternate surface form for a canonical entity.

    Example:
        `EntityAlias.objects.get(alias_normalized="openai")`
    """

    entity = models.ForeignKey(CanonicalEntity, on_delete=models.CASCADE)
    alias = models.CharField(max_length=240)
    alias_normalized = models.CharField(max_length=240, unique=True)

    class Meta:
        ordering = ["alias"]
        indexes = [
            models.Index(fields=["alias_normalized"]),
        ]

    def __str__(self) -> str:
        """Return the alias shown in admin.

        Example:
            `str(alias)`
        """
        return self.alias


class DocumentEntity(models.Model):
    """A resolved entity mention inside one document.

    Example:
        `DocumentEntity.objects.filter(document=document)`
    """

    document = models.ForeignKey(NormalizedDocument, on_delete=models.CASCADE)
    entity = models.ForeignKey(CanonicalEntity, on_delete=models.CASCADE)
    mention_text = models.CharField(max_length=240)
    mention_count = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["document_id", "entity__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "entity"],
                name="unique_document_entity",
            )
        ]

    def __str__(self) -> str:
        """Return a compact document-entity label.

        Example:
            `str(document_entity)`
        """
        return f"{self.document_id}:{self.entity_id}"


class EntityRelationship(models.Model):
    """A co-occurrence relationship between canonical entities.

    Example:
        `EntityRelationship.objects.filter(weight__gte=2)`
    """

    source_entity = models.ForeignKey(
        CanonicalEntity,
        on_delete=models.CASCADE,
        related_name="outgoing_relationships",
    )
    target_entity = models.ForeignKey(
        CanonicalEntity,
        on_delete=models.CASCADE,
        related_name="incoming_relationships",
    )
    relationship_type = models.CharField(max_length=80, default="co_occurs")
    weight = models.PositiveIntegerField(default=1)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-weight", "source_entity__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_entity", "target_entity", "relationship_type"],
                name="unique_entity_relationship",
            )
        ]

    def __str__(self) -> str:
        """Return the relationship label shown in admin.

        Example:
            `str(relationship)`
        """
        return f"{self.source_entity_id}->{self.target_entity_id}"


class DailyDigest(models.Model):
    """A generated plain-text daily digest.

    Example:
        `DailyDigest.objects.latest("digest_date")`
    """

    digest_date = models.DateField(unique=True)
    title = models.CharField(max_length=240)
    body = models.TextField()
    metrics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-digest_date"]

    def __str__(self) -> str:
        """Return the digest title.

        Example:
            `str(digest)`
        """
        return self.title


from monitoring.phase2_models import (  # noqa: E402
    AlertHit,
    AlertDetector,
    AlertFeedback,
    AlertHitDocument,
    AlertRule,
    CanonicalUrl,
    DedupeGroup,
    DiscoveryCandidate,
    DocumentEnrichment,
    DocumentTopic,
    DocumentUrlReference,
    SourceReputationSnapshot,
    TopicCluster,
)
from monitoring.operational_models import ExportArtifact, NlpRunMetric  # noqa: E402

EventCluster = TopicCluster
EventClusterDocument = DocumentTopic


class IngestionRun(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        DRY_RUN = "dry_run", "Dry run"

    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    items_seen = models.PositiveIntegerField(default=0)
    items_created = models.PositiveIntegerField(default=0)
    items_updated = models.PositiveIntegerField(default=0)
    items_skipped = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)
    cursor_before = models.CharField(max_length=1200, blank=True)
    cursor_after = models.CharField(max_length=1200, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)


class IngestedItem(models.Model):
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=512, blank=True)
    canonical_url = models.URLField(max_length=1200)
    raw_url = models.URLField(max_length=1200, blank=True)
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    author = models.CharField(max_length=300, blank=True)
    publisher = models.CharField(max_length=300, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    tags_json = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=16, blank=True)
    content_type = models.CharField(max_length=64, blank=True)
    raw_payload_json = models.JSONField(default=dict, blank=True)
    extraction_method = models.CharField(max_length=20, default="rss")
    quality_score = models.FloatField(default=0)
    dedupe_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["source", "published_at"]),
            models.Index(fields=["canonical_url"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["source", "external_id"], condition=~models.Q(external_id=""), name="uniq_source_external_id_if_exists")
        ]


class MarketInstrument(models.Model):
    symbol = models.CharField(max_length=32)
    exchange = models.CharField(max_length=32)
    name = models.CharField(max_length=255, blank=True)
    asset_class = models.CharField(max_length=64, blank=True)
    currency = models.CharField(max_length=16, blank=True)
    country = models.CharField(max_length=64, blank=True)
    sector = models.CharField(max_length=128, blank=True)
    industry = models.CharField(max_length=128, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["symbol", "exchange"], name="uniq_symbol_exchange")]


class MarketBar(models.Model):
    instrument = models.ForeignKey(MarketInstrument, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    timeframe = models.CharField(max_length=10)
    open = models.FloatField(null=True, blank=True)
    high = models.FloatField(null=True, blank=True)
    low = models.FloatField(null=True, blank=True)
    close = models.FloatField(null=True, blank=True)
    adjusted_close = models.FloatField(null=True, blank=True)
    volume = models.FloatField(null=True, blank=True)
    dollar_volume = models.FloatField(null=True, blank=True)
    trade_count = models.BigIntegerField(null=True, blank=True)
    raw_payload_json = models.JSONField(default=dict, blank=True)
    quality_flags_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["instrument", "source", "timeframe", "timestamp"], name="uniq_market_bar")]
        indexes = [models.Index(fields=["instrument", "timestamp"]), models.Index(fields=["source", "timestamp"])]


class MarketTick(models.Model):
    instrument = models.ForeignKey(MarketInstrument, on_delete=models.CASCADE)
    source = models.ForeignKey(Source, on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    price = models.FloatField(null=True, blank=True)
    bid = models.FloatField(null=True, blank=True)
    ask = models.FloatField(null=True, blank=True)
    last = models.FloatField(null=True, blank=True)
    volume = models.FloatField(null=True, blank=True)
    dollar_volume = models.FloatField(null=True, blank=True)
    trade_id = models.CharField(max_length=128, blank=True)
    raw_payload_json = models.JSONField(default=dict, blank=True)
    quality_flags_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["instrument", "source", "timestamp", "trade_id"], condition=~models.Q(trade_id=""), name="uniq_market_tick_trade")]
        indexes = [models.Index(fields=["instrument", "timestamp"]), models.Index(fields=["source", "timestamp"])]


from monitoring.finance_models import (  # noqa: E402
    CFTCCommitmentReport,
    FeatureFlagSetting,
    FinancialDataSource,
    FinancialInstrument,
    FinancialRelationEdge,
    FundamentalFact,
    FuturesContract,
    FuturesSnapshot,
    GovernmentReport,
    MacroObservation,
    MacroSeries,
    MarketSessionWindow,
    MultifractalFeatureSet,
    OptionContract,
    OptionSnapshot,
    PredictionDatasetManifest,
    StatisticalScore,
)
