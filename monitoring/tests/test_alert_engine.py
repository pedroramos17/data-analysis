"""Tests for the cluster-based intelligent alert engine."""

from datetime import timedelta
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from monitoring.models import (
    AlertDetector,
    AlertFeedback,
    AlertHit,
    AlertHitDocument,
    AlertRule,
    DocumentTopic,
    NormalizedDocument,
    RawEvent,
    Source,
    TopicCluster,
)
from monitoring.services.alert_engine import generate_alerts_for_cluster
from monitoring.services.alert_scoring import (
    compute_content_hash,
    map_score_to_severity,
    normalize_text,
)


class AlertEngineTests(TestCase):
    """Regression tests for generated, evidence-backed alert hits."""

    def test_content_hash_is_stable_for_equivalent_text(self) -> None:
        """Whitespace and case differences normalize to the same hash."""
        first_hash = compute_content_hash("  OpenAI   Security\nBreach ")
        second_hash = compute_content_hash("openai security breach")

        self.assertEqual(
            normalize_text("  OpenAI   Security\nBreach "), "openai security breach"
        )
        self.assertEqual(first_hash, second_hash)

    def test_alert_hit_requires_rule_or_detector(self) -> None:
        """AlertHit validation rejects signals with no trigger."""
        cluster = _cluster()
        alert = AlertHit(
            cluster=cluster,
            title="Missing trigger",
            severity=AlertRule.Severity.LOW,
            dedupe_hash="missing-trigger",
        )

        with self.assertRaises(ValidationError):
            alert.full_clean()

    def test_generate_alerts_for_cluster_deduplicates_hits(self) -> None:
        """Running the same cluster twice creates one materialized hit."""
        cluster = _cluster()
        _attach_document(cluster, _document())
        AlertRule.objects.create(
            name="Breach",
            rule_type=AlertRule.RuleType.KEYWORD,
            query="breach",
        )

        first_hits = generate_alerts_for_cluster(cluster.id)
        second_hits = generate_alerts_for_cluster(cluster.id)

        self.assertEqual(len(first_hits), 1)
        self.assertEqual(second_hits, [])
        self.assertEqual(AlertHit.objects.count(), 1)
        self.assertEqual(AlertHitDocument.objects.count(), 1)

    def test_severity_mapping_matches_thresholds(self) -> None:
        """Alert severity thresholds stay aligned with the spec."""
        self.assertEqual(map_score_to_severity(0.85), AlertRule.Severity.CRITICAL)
        self.assertEqual(map_score_to_severity(0.70), AlertRule.Severity.HIGH)
        self.assertEqual(map_score_to_severity(0.50), AlertRule.Severity.MEDIUM)
        self.assertEqual(map_score_to_severity(0.30), AlertRule.Severity.LOW)

    def test_generate_alert_hits_dry_run_does_not_write(self) -> None:
        """The dry-run management command leaves alert tables untouched."""
        cluster = _cluster()
        _attach_document(cluster, _document())
        AlertRule.objects.create(
            name="Breach",
            rule_type=AlertRule.RuleType.KEYWORD,
            query="breach",
        )
        output = StringIO()

        call_command("generate_alert_hits", dry_run=True, stdout=output)

        self.assertIn("would create 1 alert hits", output.getvalue())
        self.assertEqual(AlertHit.objects.count(), 0)
        self.assertEqual(AlertDetector.objects.count(), 0)

    def test_alert_status_and_feedback_actions_work(self) -> None:
        """Human-in-loop review actions update status and feedback."""
        alert = _generated_alert()

        status_response = self.client.post(
            reverse(
                "monitoring:alert-status-action",
                kwargs={"pk": alert.pk, "status": "acknowledge"},
            )
        )
        feedback_response = self.client.post(
            reverse("monitoring:alert-feedback-action", kwargs={"pk": alert.pk}),
            {"label": AlertFeedback.Label.USEFUL, "comment": "Good signal"},
        )
        alert.refresh_from_db()

        self.assertEqual(status_response.status_code, 302)
        self.assertEqual(feedback_response.status_code, 302)
        self.assertEqual(alert.status, AlertHit.Status.ACKNOWLEDGED)
        self.assertEqual(AlertFeedback.objects.count(), 1)


def _source() -> Source:
    return Source.objects.create(
        name=f"Alert Source {Source.objects.count()}",
        url=f"https://example.org/{Source.objects.count()}.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.SECURITY,
        tags=["security"],
    )


def _document() -> NormalizedDocument:
    source = _source()
    raw_event = RawEvent.objects.create(
        source=source,
        url=f"https://example.org/doc-{RawEvent.objects.count()}",
        content_hash=f"alert-raw-{RawEvent.objects.count()}",
        payload_text="{}",
    )
    return NormalizedDocument.objects.create(
        source=source,
        raw_event=raw_event,
        canonical_url=raw_event.url,
        title="OpenAI breach signal",
        content="Security breach risk grows around AI infrastructure.",
        text="Security breach risk grows around AI infrastructure.",
        entities=["OpenAI"],
        tags=["security"],
        published_at=timezone.now(),
        dedupe_hash=f"alert-doc-{raw_event.id}",
    )


def _cluster() -> TopicCluster:
    now = timezone.now()
    return TopicCluster.objects.create(
        label="breach / openai / security",
        canonical_title="OpenAI breach signal",
        summary="Security breach risk grows around AI infrastructure.",
        topic_label="breach / openai / security",
        window_start=now - timedelta(hours=1),
        window_end=now,
        keywords=["breach", "security", "openai"],
        entities=["OpenAI"],
        document_count=1,
        source_count=1,
        novelty_score=0.75,
        trend_score=0.2,
        severity_score=0.4,
        confidence_score=0.8,
    )


def _attach_document(
    cluster: TopicCluster,
    document: NormalizedDocument,
) -> DocumentTopic:
    return DocumentTopic.objects.create(
        cluster=cluster,
        document=document,
        overlap_score=0.9,
        similarity=0.9,
        role=DocumentTopic.Role.REPRESENTATIVE,
    )


def _generated_alert() -> AlertHit:
    cluster = _cluster()
    _attach_document(cluster, _document())
    AlertRule.objects.create(
        name="Breach",
        rule_type=AlertRule.RuleType.KEYWORD,
        query="breach",
    )
    return generate_alerts_for_cluster(cluster.id)[0]
