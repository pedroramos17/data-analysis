"""Canonical knowledge models for Sourceflow reasoning.

These models are additive. They do not replace the existing `monitoring`,
`quant4`, or `quantspace` tables; later phases can adapt those records into this
canonical schema.
"""

from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class TimestampedProvenanceModel(models.Model):
    """Shared timestamps and provenance for canonical records."""

    metadata_json = models.JSONField(default=dict, blank=True)
    provenance_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ProviderOwner(TimestampedProvenanceModel):
    """A provider owner or publisher group."""

    name = models.CharField(max_length=180, unique=True)
    canonical_name = models.CharField(max_length=180, unique=True)
    homepage_url = models.URLField(max_length=1200, blank=True)
    country = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["canonical_name"]
        indexes = [models.Index(fields=["canonical_name"])]

    def __str__(self) -> str:
        return self.name


class Source(TimestampedProvenanceModel):
    """Canonical source metadata for documents and evidence."""

    class SourceType(models.TextChoices):
        RSS = "rss", "RSS"
        HTML = "html", "HTML"
        API = "api", "API"
        FILING = "filing", "Filing"
        REPORT = "report", "Report"
        MANUAL = "manual", "Manual"
        MARKET_DATA = "market_data", "Market data"
        OTHER = "other", "Other"

    name = models.CharField(max_length=180, unique=True)
    url = models.URLField(max_length=1200, blank=True)
    provider_owner = models.ForeignKey(
        ProviderOwner,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sources",
    )
    source_type = models.CharField(
        max_length=40,
        choices=SourceType.choices,
        default=SourceType.OTHER,
    )
    country = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=16, default="en")
    reliability_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    bias_tags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["source_type"]),
            models.Index(fields=["country", "language"]),
        ]

    def __str__(self) -> str:
        return self.name


class Document(TimestampedProvenanceModel):
    """Canonical document record used by all extraction layers."""

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="documents")
    url = models.URLField(max_length=1200, blank=True)
    title = models.CharField(max_length=500, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    ingested_at = models.DateTimeField(default=timezone.now)
    raw_text = models.TextField(blank=True)
    clean_text = models.TextField(blank=True)
    content_hash = models.CharField(max_length=128, db_index=True)
    language = models.CharField(max_length=16, default="en")

    class Meta:
        ordering = ["-published_at", "-ingested_at", "id"]
        indexes = [
            models.Index(fields=["source", "published_at"]),
            models.Index(fields=["content_hash"]),
            models.Index(fields=["language"]),
        ]

    def __str__(self) -> str:
        return self.title or self.url or f"document:{self.pk}"


class DocumentChunk(TimestampedProvenanceModel):
    """Text chunk with parent-document provenance."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    char_start = models.PositiveIntegerField(default=0)
    char_end = models.PositiveIntegerField(default=0)
    token_count = models.PositiveIntegerField(default=0)
    content_hash = models.CharField(max_length=128, blank=True)
    language = models.CharField(max_length=16, blank=True)
    ingestion_version = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="uniq_sourceflow_document_chunk",
            )
        ]
        indexes = [models.Index(fields=["document", "chunk_index"])]

    def __str__(self) -> str:
        return f"{self.document_id}:{self.chunk_index}"


class EvidenceSpan(TimestampedProvenanceModel):
    """Exact text span supporting an extracted object."""

    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="evidence_spans")
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="evidence_spans",
    )
    chunk = models.ForeignKey(
        DocumentChunk,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidence_spans",
    )
    text = models.TextField()
    char_start = models.PositiveIntegerField(default=0)
    char_end = models.PositiveIntegerField(default=0)
    extractor_name = models.CharField(max_length=120, default="manual")
    extractor_version = models.CharField(max_length=80, blank=True)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    class Meta:
        ordering = ["document_id", "char_start", "id"]
        indexes = [
            models.Index(fields=["document", "char_start"]),
            models.Index(fields=["source", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.document_id}:{self.char_start}-{self.char_end}"


class Entity(TimestampedProvenanceModel):
    """Canonical entity used by claims, events, and graph nodes."""

    canonical_name = models.CharField(max_length=240)
    entity_type = models.CharField(max_length=80, default="Unknown")
    external_ids_json = models.JSONField(default=dict, blank=True)
    country = models.CharField(max_length=80, blank=True)
    sector = models.CharField(max_length=128, blank=True)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )

    class Meta:
        ordering = ["canonical_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["canonical_name", "entity_type"],
                name="uniq_sourceflow_entity_identity",
            )
        ]
        indexes = [models.Index(fields=["entity_type", "canonical_name"])]

    def __str__(self) -> str:
        return self.canonical_name


class EntityAlias(TimestampedProvenanceModel):
    """Surface form or external alias for an entity."""

    entity = models.ForeignKey(Entity, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=240)
    alias_normalized = models.CharField(max_length=240)
    alias_type = models.CharField(max_length=40, default="name")
    namespace = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["alias_normalized"]
        constraints = [
            models.UniqueConstraint(
                fields=["alias_normalized", "namespace"],
                name="uniq_sourceflow_entity_alias_namespace",
            )
        ]
        indexes = [models.Index(fields=["alias_normalized", "namespace"])]

    def __str__(self) -> str:
        return self.alias


class EntityMention(TimestampedProvenanceModel):
    """Candidate or linked entity mention in a document."""

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="entity_mentions",
    )
    chunk = models.ForeignKey(
        DocumentChunk,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entity_mentions",
    )
    entity = models.ForeignKey(
        Entity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mentions",
    )
    evidence_span = models.ForeignKey(
        EvidenceSpan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entity_mentions",
    )
    mention_text = models.CharField(max_length=240)
    entity_type = models.CharField(max_length=80, default="Unknown")
    char_start = models.PositiveIntegerField(default=0)
    char_end = models.PositiveIntegerField(default=0)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    extractor_name = models.CharField(max_length=120, default="manual")
    extractor_version = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=40, default="candidate")

    class Meta:
        ordering = ["document_id", "char_start", "id"]
        indexes = [
            models.Index(fields=["document", "char_start"]),
            models.Index(fields=["entity", "document"]),
        ]

    def __str__(self) -> str:
        return self.mention_text


class AssumptionPolicy(TimestampedProvenanceModel):
    """Named open-world or closed-world policy."""

    class PolicyCode(models.TextChoices):
        OWA = "OWA", "Open-world assumption"
        CWA = "CWA", "Closed-world assumption"
        PARTIAL_CWA = "PartialCWA", "Partial closed-world assumption"
        CAREFUL_CWA = "CarefulCWA", "Careful closed-world assumption"
        GCWA = "GCWA", "Generalized closed-world assumption"
        EGCWA = "EGCWA", "Extended generalized closed-world assumption"
        EXTENDED_CWA = "ExtendedCWA", "Extended closed-world assumption"
        UNIQUE_NAME = "UniqueNameAssumption", "Unique-name assumption"
        NO_UNIQUE_NAME = "NoUniqueNameAssumption", "No unique-name assumption"

    code = models.CharField(max_length=40, choices=PolicyCode.choices, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    scope = models.CharField(max_length=120, blank=True)
    is_default = models.BooleanField(default=False)
    params_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["code"]
        indexes = [models.Index(fields=["code", "scope"])]

    def __str__(self) -> str:
        return self.code


class InferenceRule(TimestampedProvenanceModel):
    """Persisted rule definition used to derive beliefs."""

    class RuleType(models.TextChoices):
        DEDUCTIVE = "deductive", "Deductive"
        DEFAULT = "default", "Default"
        ABDUCTIVE = "abductive", "Abductive"
        DIAGNOSTIC = "diagnostic", "Diagnostic"
        RISK_PROPAGATION = "risk_propagation", "Risk propagation"
        SOURCE_COMPARISON = "source_comparison", "Source comparison"
        RETRIEVAL_EXPANSION = "retrieval_expansion", "Retrieval expansion"

    rule_id = models.CharField(max_length=160, unique=True)
    name = models.CharField(max_length=180)
    rule_type = models.CharField(
        max_length=40,
        choices=RuleType.choices,
        default=RuleType.DEDUCTIVE,
    )
    definition_json = models.JSONField(default=dict, blank=True)
    confidence_delta = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    assumption_policy = models.ForeignKey(
        AssumptionPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rules",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["rule_id"]
        indexes = [models.Index(fields=["rule_type", "is_active"])]

    def __str__(self) -> str:
        return self.rule_id


class Claim(TimestampedProvenanceModel):
    """Structured source claim with exact evidence."""

    class Polarity(models.TextChoices):
        POSITIVE = "positive", "Positive"
        NEGATIVE = "negative", "Negative"
        NEUTRAL = "neutral", "Neutral"
        UNKNOWN = "unknown", "Unknown"

    class Modality(models.TextChoices):
        ASSERTED = "asserted", "Asserted"
        ALLEGED = "alleged", "Alleged"
        DENIED = "denied", "Denied"
        FORECASTED = "forecasted", "Forecasted"
        RUMORED = "rumored", "Rumored"
        CONFIRMED = "confirmed", "Confirmed"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INCOMPLETE = "incomplete", "Incomplete"
        RETRACTED = "retracted", "Retracted"
        DISPUTED = "disputed", "Disputed"
        STALE = "stale", "Stale"

    subject_entity = models.ForeignKey(
        Entity,
        on_delete=models.PROTECT,
        related_name="subject_claims",
    )
    predicate = models.CharField(max_length=160)
    object_entity = models.ForeignKey(
        Entity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="object_claims",
    )
    object_literal = models.TextField(blank=True)
    polarity = models.CharField(
        max_length=20,
        choices=Polarity.choices,
        default=Polarity.UNKNOWN,
    )
    modality = models.CharField(
        max_length=20,
        choices=Modality.choices,
        default=Modality.ASSERTED,
    )
    tense = models.CharField(max_length=40, blank=True)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="claims")
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="claims")
    evidence_span = models.ForeignKey(
        EvidenceSpan,
        on_delete=models.PROTECT,
        related_name="claims",
    )
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["subject_entity", "predicate"]),
            models.Index(fields=["source", "created_at"]),
            models.Index(fields=["document", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.subject_entity_id}:{self.predicate}"


class Event(TimestampedProvenanceModel):
    """Structured market-relevant event with exact evidence."""

    class EventType(models.TextChoices):
        EARNINGS = "earnings", "Earnings"
        GUIDANCE = "guidance", "Guidance"
        LAWSUIT = "lawsuit", "Lawsuit"
        REGULATORY_ACTION = "regulatory_action", "Regulatory action"
        MERGER_ACQUISITION = "merger_acquisition", "Merger or acquisition"
        SUPPLY_CHAIN_DISRUPTION = "supply_chain_disruption", "Supply-chain disruption"
        PRODUCT_LAUNCH = "product_launch", "Product launch"
        EXECUTIVE_CHANGE = "executive_change", "Executive change"
        CREDIT_EVENT = "credit_event", "Credit event"
        MACRO_EVENT = "macro_event", "Macro event"
        COMMODITY_SHOCK = "commodity_shock", "Commodity shock"
        CURRENCY_SHOCK = "currency_shock", "Currency shock"
        GEOPOLITICAL_EVENT = "geopolitical_event", "Geopolitical event"
        ANALYST_REVISION = "analyst_revision", "Analyst revision"
        INSIDER_TRANSACTION = "insider_transaction", "Insider transaction"
        LIQUIDITY_EVENT = "liquidity_event", "Liquidity event"
        LOB_ANOMALY = "lob_anomaly", "LOB anomaly"
        OTHER = "other", "Other"

    actor_entity = models.ForeignKey(
        Entity,
        on_delete=models.PROTECT,
        related_name="actor_events",
    )
    predicate = models.CharField(max_length=160)
    object_entity = models.ForeignKey(
        Entity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="object_events",
    )
    object_literal = models.TextField(blank=True)
    event_type = models.CharField(
        max_length=60,
        choices=EventType.choices,
        default=EventType.OTHER,
    )
    event_time = models.DateTimeField(null=True, blank=True)
    extraction_time = models.DateTimeField(default=timezone.now)
    polarity = models.CharField(
        max_length=20,
        choices=Claim.Polarity.choices,
        default=Claim.Polarity.UNKNOWN,
    )
    magnitude = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="events")
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="events")
    evidence_span = models.ForeignKey(
        EvidenceSpan,
        on_delete=models.PROTECT,
        related_name="events",
    )

    class Meta:
        ordering = ["-event_time", "-created_at", "id"]
        indexes = [
            models.Index(fields=["actor_entity", "event_type"]),
            models.Index(fields=["source", "event_time"]),
            models.Index(fields=["document", "event_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.actor_entity_id}:{self.event_type}:{self.predicate}"


class KnowledgeEdge(TimestampedProvenanceModel):
    """SQL-backed graph edge with provenance."""

    edge_type = models.CharField(max_length=80)
    source_node_type = models.CharField(max_length=80)
    source_node_id = models.CharField(max_length=160)
    target_node_type = models.CharField(max_length=80)
    target_node_id = models.CharField(max_length=160)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    source_document = models.ForeignKey(
        Document,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_edges",
    )
    evidence_span = models.ForeignKey(
        EvidenceSpan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_edges",
    )
    observed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["source_node_type", "source_node_id", "edge_type"]
        indexes = [
            models.Index(fields=["source_node_type", "source_node_id"]),
            models.Index(fields=["target_node_type", "target_node_id"]),
            models.Index(fields=["edge_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.source_node_type}:{self.source_node_id} -{self.edge_type}-> {self.target_node_type}:{self.target_node_id}"


class Belief(TimestampedProvenanceModel):
    """Derived or asserted belief with explicit assumption policy."""

    class TruthStatus(models.TextChoices):
        TRUE_SUPPORTED = "true_supported", "True supported"
        FALSE_SUPPORTED = "false_supported", "False supported"
        CONTRADICTED = "contradicted", "Contradicted"
        UNKNOWN = "unknown", "Unknown"
        PARTIALLY_SUPPORTED = "partially_supported", "Partially supported"
        SOURCE_DISPUTED = "source_disputed", "Source disputed"
        TIME_EXPIRED = "time_expired", "Time expired"
        REQUIRES_HUMAN_REVIEW = "requires_human_review", "Requires human review"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        STALE = "stale", "Stale"
        RETRACTED = "retracted", "Retracted"
        SUPERSEDED = "superseded", "Superseded"

    belief_type = models.CharField(max_length=80)
    subject_entity = models.ForeignKey(
        Entity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="subject_beliefs",
    )
    predicate = models.CharField(max_length=160)
    object_entity = models.ForeignKey(
        Entity,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="object_beliefs",
    )
    object_literal = models.TextField(blank=True)
    truth_status = models.CharField(
        max_length=40,
        choices=TruthStatus.choices,
        default=TruthStatus.UNKNOWN,
    )
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    assumption_policy = models.ForeignKey(
        AssumptionPolicy,
        on_delete=models.PROTECT,
        related_name="beliefs",
    )
    created_by_rule = models.ForeignKey(
        InferenceRule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_beliefs",
    )
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["belief_type", "truth_status"]),
            models.Index(fields=["subject_entity", "predicate"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.belief_type}:{self.predicate}:{self.truth_status}"


class Justification(TimestampedProvenanceModel):
    """Support or contradiction edge for a belief."""

    class SupportType(models.TextChoices):
        SUPPORTS = "supports", "Supports"
        CONTRADICTS = "contradicts", "Contradicts"
        DERIVED_BY_RULE = "derived_by_rule", "Derived by rule"
        ASSUMPTION = "assumption", "Assumption"

    belief = models.ForeignKey(Belief, on_delete=models.CASCADE, related_name="justifications")
    support_type = models.CharField(
        max_length=40,
        choices=SupportType.choices,
        default=SupportType.SUPPORTS,
    )
    supporting_claim = models.ForeignKey(
        Claim,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="justifications",
    )
    supporting_event = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="justifications",
    )
    supporting_belief = models.ForeignKey(
        Belief,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supporting_justifications",
    )
    rule = models.ForeignKey(
        InferenceRule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="justifications",
    )
    weight = models.DecimalField(max_digits=6, decimal_places=3, default=1)

    class Meta:
        ordering = ["belief_id", "support_type", "id"]
        indexes = [models.Index(fields=["belief", "support_type"])]

    def __str__(self) -> str:
        return f"{self.belief_id}:{self.support_type}"


class RetractionLog(TimestampedProvenanceModel):
    """Audit row for claim, event, entity, or belief retractions."""

    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=160)
    reason = models.TextField()
    previous_status = models.CharField(max_length=80, blank=True)
    new_status = models.CharField(max_length=80, blank=True)
    source = models.ForeignKey(
        Source,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retraction_logs",
    )
    document = models.ForeignKey(
        Document,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retraction_logs",
    )
    affected_claim = models.ForeignKey(
        Claim,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retraction_logs",
    )
    affected_event = models.ForeignKey(
        Event,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retraction_logs",
    )
    affected_belief = models.ForeignKey(
        Belief,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retraction_logs",
    )
    retracted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-retracted_at", "id"]
        indexes = [models.Index(fields=["target_type", "target_id"])]

    def __str__(self) -> str:
        return f"{self.target_type}:{self.target_id}"


class RetrievalTrace(TimestampedProvenanceModel):
    """Trace for a retrieval or GraphRAG query."""

    query = models.TextField()
    query_hash = models.CharField(max_length=128, db_index=True)
    retriever_name = models.CharField(max_length=120, default="manual")
    retrieval_mode = models.CharField(max_length=80, blank=True)
    results_json = models.JSONField(default=list, blank=True)
    citations_json = models.JSONField(default=list, blank=True)
    assumptions_json = models.JSONField(default=list, blank=True)
    retrieval_confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    extraction_confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reasoning_confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["retriever_name", "created_at"])]

    def __str__(self) -> str:
        return self.query[:120]


class RiskFactor(TimestampedProvenanceModel):
    """Canonical risk factor used by risk graph reasoning."""

    name = models.CharField(max_length=180, unique=True)
    risk_type = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        ordering = ["risk_type", "name"]
        indexes = [models.Index(fields=["risk_type"])]

    def __str__(self) -> str:
        return self.name


class Asset(TimestampedProvenanceModel):
    """Canonical investable or referenced asset."""

    symbol = models.CharField(max_length=80)
    name = models.CharField(max_length=240, blank=True)
    asset_type = models.CharField(max_length=80, default="equity")
    country = models.CharField(max_length=80, blank=True)
    sector = models.CharField(max_length=128, blank=True)
    currency = models.CharField(max_length=16, blank=True)
    external_ids_json = models.JSONField(default=dict, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        ordering = ["symbol", "asset_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "asset_type"],
                name="uniq_sourceflow_asset_symbol_type",
            )
        ]
        indexes = [models.Index(fields=["symbol", "asset_type"])]

    def __str__(self) -> str:
        return self.symbol


class Instrument(TimestampedProvenanceModel):
    """Tradable instrument for an asset."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="instruments")
    symbol = models.CharField(max_length=80)
    instrument_type = models.CharField(max_length=80, default="equity")
    exchange = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=16, blank=True)
    external_ids_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["symbol", "exchange", "instrument_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "exchange", "instrument_type"],
                name="uniq_sourceflow_instrument_identity",
            )
        ]
        indexes = [models.Index(fields=["symbol", "exchange"])]

    def __str__(self) -> str:
        return self.symbol


class PortfolioPosition(TimestampedProvenanceModel):
    """Controlled internal portfolio position."""

    portfolio_id = models.CharField(max_length=160)
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="portfolio_positions",
    )
    instrument = models.ForeignKey(
        Instrument,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="portfolio_positions",
    )
    quantity = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    market_value = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    currency = models.CharField(max_length=16, blank=True)
    as_of = models.DateTimeField(default=timezone.now)
    assumption_policy = models.ForeignKey(
        AssumptionPolicy,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="portfolio_positions",
    )

    class Meta:
        ordering = ["portfolio_id", "asset_id", "-as_of"]
        indexes = [
            models.Index(fields=["portfolio_id", "as_of"]),
            models.Index(fields=["asset", "as_of"]),
        ]

    def __str__(self) -> str:
        return f"{self.portfolio_id}:{self.asset_id}"
