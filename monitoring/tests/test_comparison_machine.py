"""Tests for the deterministic comparison-machine foundation."""

from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from monitoring.models import (
    Claim,
    DocumentTopic,
    NormalizedDocument,
    Owner,
    Provider,
    RawEvent,
    Source,
    TopicCluster,
)
from monitoring.services.comparisons import compare_event_coverage
from monitoring.services.deduplication import (
    canonicalize_article_url,
    content_hash,
    hamming_distance,
    simhash_text,
    url_hash,
)
from monitoring.services.events import cluster_articles_into_events


class DeduplicationHelperTests(SimpleTestCase):
    """Regression tests for explainable article deduplication."""

    def test_url_and_content_hashes_are_stable(self) -> None:
        """Tracking parameters do not affect article URL identity."""
        first_url = "HTTPS://Example.Org:443/news/?utm_source=x&b=2&a=1#section"
        second_url = "https://example.org/news?a=1&b=2"

        canonical_url = canonicalize_article_url(first_url)

        self.assertEqual(canonical_url, second_url)
        self.assertEqual(url_hash(first_url), url_hash(second_url))
        self.assertEqual(content_hash("A  claim\nhere"), content_hash("a claim here"))

    def test_simhash_separates_near_and_unrelated_text(self) -> None:
        """Near duplicates have lower Hamming distance than unrelated articles."""
        first = simhash_text("OpenAI launched a safety model in Paris today.")
        second = simhash_text("Today in Paris, OpenAI launched its safety model.")
        unrelated = simhash_text("Soybean futures fell after heavy rain forecasts.")

        near_distance = hamming_distance(first, second)
        unrelated_distance = hamming_distance(first, unrelated)

        self.assertLessEqual(near_distance, 18)
        self.assertGreater(unrelated_distance, near_distance)


class EventClusteringTests(TestCase):
    """Regression tests for deterministic event clustering."""

    def test_related_articles_link_to_one_event_with_reason_json(self) -> None:
        """Articles with title and entity overlap share one explainable event."""
        _article("Wire A", "OpenAI launches Paris model", "OpenAI launched in Paris.")
        _article("Wire B", "Paris OpenAI model launch", "Paris saw OpenAI launch.")

        summary = cluster_articles_into_events(window_hours=24, min_link_score=0.35)

        links = DocumentTopic.objects.order_by("document_id")
        self.assertEqual(summary.created_clusters, 1)
        self.assertEqual(TopicCluster.objects.count(), 1)
        self.assertEqual(links.count(), 2)
        self.assertIn("entity_score", links[1].link_reason)
        self.assertIn("title_score", links[1].link_reason)
        self.assertGreaterEqual(float(links[1].similarity), 0.35)

    def test_unrelated_articles_create_separate_micro_clusters(self) -> None:
        """Unrelated articles do not merge just because they share a time window."""
        _article("Energy Wire", "Oil supply outlook", "OPEC discussed oil output.")
        _article("Health Wire", "Hospital capacity update", "WHO reviewed clinics.")

        summary = cluster_articles_into_events(window_hours=24, min_link_score=0.50)

        self.assertEqual(summary.created_clusters, 2)
        self.assertEqual(summary.linked_articles, 2)
        self.assertEqual(TopicCluster.objects.count(), 2)


class EventComparisonTests(TestCase):
    """Regression tests for provider-level event comparison."""

    def test_comparison_snapshot_is_comparative_and_neutral(self) -> None:
        """Claims and omissions are phrased as coverage comparisons."""
        owner = Owner.objects.create(
            name="Example Owner", canonical_name="example owner"
        )
        provider_a = Provider.objects.create(name="Provider A", owner=owner)
        provider_b = Provider.objects.create(name="Provider B", owner=owner)
        event = _event("OpenAI Paris launch")
        first = _article("Feed A", "OpenAI launch", "OpenAI launched.", provider_a)
        second = _article("Feed B", "OpenAI launch", "OpenAI launched.", provider_b)
        _link(event, first)
        _link(event, second)
        _claim(first, "OpenAI launched a model in Paris.")
        _claim(first, "Executives said the model lowers latency.")
        _claim(second, "OpenAI launched a model in Paris.")

        snapshot = compare_event_coverage(event, omission_threshold=0.50)

        payload = snapshot.payload
        omissions = " ".join(payload["omissions"]["claims"])
        self.assertEqual(
            payload["coverage"]["providers"]["Provider A"]["article_count"], 1
        )
        self.assertIn("OpenAI launched a model in Paris.", payload["claims"]["shared"])
        self.assertIn(
            "Executives said the model lowers latency.",
            payload["claims"]["unique_by_provider"]["Provider A"],
        )
        self.assertIn("covered the event but did not mention claim", omissions)
        self.assertNotIn("hid", omissions.lower())
        self.assertNotIn("truth", omissions.lower())
        self.assertEqual(payload["amplification"]["Provider A"]["score"], 1.0)


class ComparisonExportTests(TestCase):
    """Regression tests for comparison-machine Parquet row builders."""

    def test_supported_export_datasets_return_rows(self) -> None:
        """All comparison datasets expose Arrow-friendly row dictionaries."""
        from monitoring.exporters import SUPPORTED_EXPORT_DATASETS, export_dataset_rows

        event = _event("Exportable event")
        article = _article("Export Feed", "Export title", "Export content")
        _link(event, article)
        _claim(article, "Export claim.")
        compare_event_coverage(event)

        datasets = set(SUPPORTED_EXPORT_DATASETS)

        self.assertIn("articles", datasets)
        self.assertIn("event_comparison_snapshots", datasets)
        self.assertIn("provider_name", export_dataset_rows("articles")[0])
        self.assertIn("canonical_title", export_dataset_rows("events")[0])


def _source(name: str, provider: Provider | None = None) -> Source:
    provider = provider or Provider.objects.create(name=f"{name} Provider")
    return Source.objects.create(
        name=name,
        url=f"https://example.org/{name.lower().replace(' ', '-')}.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.WORLD,
        provider=provider,
    )


def _article(
    source_name: str,
    title: str,
    content: str,
    provider: Provider | None = None,
) -> NormalizedDocument:
    source = _source(source_name, provider)
    raw_event = RawEvent.objects.create(
        source=source,
        url=f"https://example.org/articles/{RawEvent.objects.count()}",
        content_hash=f"raw-{RawEvent.objects.count()}",
        payload_text="{}",
    )
    return NormalizedDocument.objects.create(
        source=source,
        raw_event=raw_event,
        url=raw_event.url,
        canonical_url=raw_event.url,
        title=title,
        content=content,
        text=content,
        extracted_text=content,
        published_at=timezone.now() - timedelta(minutes=RawEvent.objects.count()),
        fetched_at=timezone.now(),
        dedupe_hash=f"doc-{raw_event.id}",
    )


def _event(label: str) -> TopicCluster:
    now = timezone.now()
    return TopicCluster.objects.create(
        label=label,
        canonical_title=label,
        window_start=now - timedelta(hours=1),
        window_end=now,
    )


def _link(event: TopicCluster, article: NormalizedDocument) -> DocumentTopic:
    return DocumentTopic.objects.create(
        cluster=event,
        document=article,
        similarity=1,
        overlap_score=1,
        link_reason={"test": "manual"},
    )


def _claim(article: NormalizedDocument, text: str) -> Claim:
    return Claim.objects.create(
        article=article,
        claim_text=text,
        normalized_claim=text.lower(),
        backend="test",
    )
