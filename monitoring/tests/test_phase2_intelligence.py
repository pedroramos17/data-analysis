"""Tests for Phase 2 enrichment, discovery, alerts, topics, and reputation."""

from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from monitoring.alerts import evaluate_alert_rules
from monitoring.discovery import approve_discovery_candidate, discover_source_candidates
from monitoring.enrichment import enrich_document
from monitoring.models import (
    AlertHit,
    AlertRule,
    DiscoveryCandidate,
    DocumentEnrichment,
    DocumentTopic,
    IngestionCheckpoint,
    NormalizedDocument,
    RawEvent,
    Source,
    SourceReputationSnapshot,
    TopicCluster,
)
from monitoring.reputation import score_source
from monitoring.topics import cluster_topics


class EnrichmentTests(TestCase):
    """Regression tests for local deterministic enrichment."""

    def test_enrichment_extracts_local_nlp_fields(self) -> None:
        """Enrichment detects language, keywords, hashtags, summary, and sentiment."""
        document = _document(content="The secure market shows growth. #AI #Markets")

        changed = enrich_document(document)

        enrichment = DocumentEnrichment.objects.get(document=document)
        self.assertTrue(changed)
        self.assertEqual(enrichment.detected_language, "en")
        self.assertIn("secure", enrichment.keywords)
        self.assertIn("#ai", enrichment.hashtags)
        self.assertGreater(enrichment.sentiment_score, 0)

    def test_enrichment_is_idempotent_without_force(self) -> None:
        """Existing enrichment is skipped unless force is requested."""
        document = _document()

        first = enrich_document(document)
        second = enrich_document(document)

        self.assertTrue(first)
        self.assertFalse(second)

    def test_enrichment_detects_quality_flags(self) -> None:
        """Missing or short content is captured as data-quality flags."""
        document = _document(content="short")
        document.published_at = None
        document.save(update_fields=["published_at"])

        enrich_document(document)

        flags = DocumentEnrichment.objects.get(document=document).quality_flags
        self.assertIn("missing_published_at", flags)
        self.assertIn("short_content", flags)


class DiscoveryTests(TestCase):
    """Regression tests for local discovery candidates."""

    def test_discovers_rss_hints_and_deduplicates(self) -> None:
        """RSS URLs in document text create one candidate only."""
        _document(content="Follow https://example.org/feed.xml for updates.")

        first_count = discover_source_candidates(limit=10)
        second_count = discover_source_candidates(limit=10)

        self.assertGreaterEqual(first_count, 1)
        self.assertEqual(second_count, 0)
        self.assertTrue(
            DiscoveryCandidate.objects.filter(candidate_type="rss").exists()
        )

    def test_approving_candidate_creates_disabled_source(self) -> None:
        """Admin approval creates a disabled Source row for review."""
        candidate = DiscoveryCandidate.objects.create(
            candidate_type=DiscoveryCandidate.CandidateType.RSS,
            name="Candidate Feed",
            url="https://example.org/feed.xml",
            category=Source.Category.SECURITY,
            tags=["security"],
            confidence=0.8,
        )

        source = approve_discovery_candidate(candidate)

        self.assertFalse(source.is_enabled)
        self.assertEqual(source.source_type, Source.SourceType.RSS)
        self.assertEqual(source.tags, ["security"])


class AlertTests(TestCase):
    """Regression tests for in-app alert rules."""

    def test_keyword_entity_category_and_volume_rules_create_hits(self) -> None:
        """Alert evaluation supports all Phase 2 rule types."""
        document = _document(content="Security breach risk for OpenAI systems.")
        enrich_document(document)
        _rules()

        created_count = evaluate_alert_rules(lookback_hours=24)

        self.assertEqual(created_count, 4)
        self.assertEqual(AlertHit.objects.count(), 4)
        self.assertTrue(
            AlertHit.objects.filter(
                trigger_type=AlertHit.TriggerType.EXPLICIT_RULE_MATCH
            ).exists()
        )

    def test_alert_deduplication_and_cooldown_prevent_repeats(self) -> None:
        """Repeated evaluation does not create duplicate hits."""
        document = _document(content="Security breach risk for OpenAI systems.")
        enrich_document(document)
        AlertRule.objects.create(
            name="Breach",
            rule_type=AlertRule.RuleType.KEYWORD,
            query="breach",
            cooldown_minutes=60,
        )

        first_count = evaluate_alert_rules(lookback_hours=24)
        second_count = evaluate_alert_rules(lookback_hours=24)

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)

    def test_alert_page_returns_success(self) -> None:
        """The in-app alert review page renders."""
        response = self.client.get(reverse("monitoring:alert-hit-list"))

        self.assertEqual(response.status_code, 200)


class TopicTests(TestCase):
    """Regression tests for deterministic topic clustering."""

    def test_similar_documents_cluster_together(self) -> None:
        """Documents sharing local keywords/entities form one cluster."""
        _document(
            title="Security breach at OpenAI", content="Security breach risk grows."
        )
        _document(
            title="OpenAI breach response", content="Security breach response improves."
        )
        _document(
            title="Central bank policy",
            content="Rates and inflation outlook.",
            entities=["Federal Reserve"],
        )

        cluster_count = cluster_topics(window_hours=72, min_documents=2)

        self.assertEqual(cluster_count, 1)
        self.assertEqual(TopicCluster.objects.count(), 1)
        self.assertEqual(DocumentTopic.objects.count(), 2)

    def test_unrelated_documents_do_not_cluster(self) -> None:
        """Unrelated documents below overlap threshold stay unclustered."""
        _document(
            title="Energy outlook", content="Oil supply report.", entities=["OPEC"]
        )
        _document(
            title="Health update", content="Hospital capacity report.", entities=["WHO"]
        )

        cluster_count = cluster_topics(window_hours=72, min_documents=2)

        self.assertEqual(cluster_count, 0)


class ReputationTests(TestCase):
    """Regression tests for source reputation scoring."""

    def test_reputation_score_is_bounded_and_updates_source(self) -> None:
        """Source score persists to snapshot and source row."""
        source = _source(source_tier=1)
        document = _document(source=source)
        enrich_document(document)

        score = score_source(source, window_days=30)
        source.refresh_from_db()

        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 1)
        self.assertEqual(source.reputation_score, score)
        self.assertEqual(SourceReputationSnapshot.objects.count(), 1)

    def test_failures_and_cooldown_reduce_reputation(self) -> None:
        """A cooling-down source scores below a healthy source."""
        healthy_source = _source(name="Healthy", source_tier=1)
        failing_source = _source(name="Failing", source_tier=1)
        IngestionCheckpoint.objects.create(
            source=failing_source,
            consecutive_failures=3,
            cooldown_until=timezone.now() + timedelta(minutes=5),
        )

        healthy_score = score_source(healthy_source)
        failing_score = score_source(failing_source)

        self.assertLess(failing_score, healthy_score)


def _rules() -> None:
    AlertRule.objects.create(name="Keyword", rule_type="keyword", query="breach")
    AlertRule.objects.create(name="Entity", rule_type="entity", query="OpenAI")
    AlertRule.objects.create(name="Category", rule_type="category", category="security")
    AlertRule.objects.create(name="Volume", rule_type="volume", threshold_count=1)


def _source(name: str = "Example Source", source_tier: int = 2) -> Source:
    return Source.objects.create(
        name=name,
        url=f"https://example.org/{name}.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.SECURITY,
        source_tier=source_tier,
        tags=["security"],
    )


def _document(
    source: Source | None = None,
    title: str = "OpenAI Security Update",
    content: str = "Security breach risk improves with secure growth.",
    published_at: datetime | None = None,
    entities: list[str] | None = None,
) -> NormalizedDocument:
    source = source or _source(name=f"Source {RawEvent.objects.count()}")
    raw_event = RawEvent.objects.create(
        source=source,
        url=f"https://example.org/{RawEvent.objects.count()}",
        content_hash=f"raw-{RawEvent.objects.count()}",
        payload_text="{}",
    )
    return NormalizedDocument.objects.create(
        source=source,
        raw_event=raw_event,
        canonical_url=raw_event.url,
        title=title,
        published_at=published_at or timezone.now(),
        content=content,
        entities=entities or ["OpenAI"],
        tags=["security"],
        dedupe_hash=f"doc-{raw_event.id}",
    )
