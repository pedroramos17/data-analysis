"""Tests for dashboard routes and synchronous POST actions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.urls import reverse

from monitoring.models import (
    AlertHit,
    DiscoveryCandidate,
    ExportArtifact,
    NlpRunMetric,
    NormalizedDocument,
    RawEvent,
    Source,
)


class DashboardActionTests(TestCase):
    """Regression tests for browser-triggered operations."""

    def test_dashboard_and_documents_routes_render(self) -> None:
        """Root renders dashboard and documents moved to `/documents/`."""
        dashboard_response = self.client.get(reverse("monitoring:dashboard"))
        documents_response = self.client.get(reverse("monitoring:document-list"))

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "Operations Dashboard")
        self.assertEqual(documents_response.status_code, 200)

    def test_dashboard_post_actions_redirect(self) -> None:
        """Maintenance action buttons call local services and redirect."""
        action_names = (
            "enrich-documents-action",
            "discover-sources-action",
            "evaluate-alerts-action",
            "cluster-topics-action",
            "score-source-reputation-action",
        )

        for action_name in action_names:
            response = self.client.post(reverse(f"monitoring:{action_name}"))
            self.assertEqual(response.status_code, 302)

    def test_nlp_post_action_saves_metric_and_session_json(self) -> None:
        """Dashboard NLP action persists metric and stores latest JSON."""
        response = self.client.post(
            reverse("monitoring:nlp-pipeline-action"),
            {"text": "OpenAI reports secure growth. #AI", "tasks": "all"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(NlpRunMetric.objects.count(), 1)
        self.assertIn("latest_nlp_result", self.client.session)

    def test_export_post_action_creates_artifact_and_preview(self) -> None:
        """Dashboard export action creates a visible Parquet artifact."""
        _document()
        with TemporaryDirectory() as directory:
            with override_settings(PARQUET_EXPORT_DIR=Path(directory)):
                response = self.client.post(reverse("monitoring:export-parquet-action"))
                artifact = ExportArtifact.objects.get()
                detail_response = self.client.get(
                    reverse(
                        "monitoring:export-artifact-detail",
                        kwargs={"pk": artifact.pk},
                    )
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(artifact.row_count, 1)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Dynamic Preview")

    def test_candidate_page_and_actions_render(self) -> None:
        """Discovered candidates are visible and reviewable outside admin."""
        candidate = DiscoveryCandidate.objects.create(
            candidate_type=DiscoveryCandidate.CandidateType.RSS,
            name="Dashboard Candidate",
            url="https://example.org/candidate.xml",
            category=Source.Category.SECURITY,
            tags=["security"],
        )

        list_response = self.client.get(reverse("monitoring:discovery-candidate-list"))
        approve_response = self.client.post(
            reverse(
                "monitoring:approve-candidate-action",
                kwargs={"pk": candidate.pk},
            )
        )
        candidate.refresh_from_db()

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Dashboard Candidate")
        self.assertEqual(approve_response.status_code, 302)
        self.assertEqual(candidate.status, DiscoveryCandidate.Status.APPROVED)

    def test_parquet_rows_endpoint_returns_dynamic_rows(self) -> None:
        """The Parquet viewer JSON endpoint supports bounded table previews."""
        _document()
        with TemporaryDirectory() as directory:
            with override_settings(PARQUET_EXPORT_DIR=Path(directory)):
                _response = self.client.post(
                    reverse("monitoring:export-parquet-action")
                )
                artifact = ExportArtifact.objects.get()
                rows_response = self.client.get(
                    reverse(
                        "monitoring:export-artifact-rows-api",
                        kwargs={"pk": artifact.pk},
                    ),
                    {"search": "Dashboard", "page_size": "5"},
                )

        self.assertEqual(rows_response.status_code, 200)
        payload = rows_response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["rows"][0]["title"], "Dashboard Document")

    def test_evaluate_alerts_action_creates_detector_backed_hits(self) -> None:
        """The dashboard alert action runs clustering plus automatic detectors."""
        _document(title="AI startup funding spike")
        _document(title="Venture AI startup funding")
        _document(title="Startup AI platform funding")

        response = self.client.post(reverse("monitoring:evaluate-alerts-action"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(AlertHit.objects.filter(detector__isnull=False).exists())


def _source() -> Source:
    unique = Source.objects.count()
    return Source.objects.create(
        name=f"Dashboard Source {unique}",
        url=f"https://example.org/feed-{unique}.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.SECURITY,
        tags=["security"],
    )


def _document(title: str = "Dashboard Document") -> NormalizedDocument:
    source = _source()
    unique = RawEvent.objects.count()
    raw_event = RawEvent.objects.create(
        source=source,
        url=f"https://example.org/dashboard-{unique}",
        content_hash=f"dashboard-raw-{unique}",
        payload_text="{}",
    )
    return NormalizedDocument.objects.create(
        source=source,
        raw_event=raw_event,
        canonical_url=raw_event.url,
        title=title,
        published_at=datetime(2026, 5, 9, tzinfo=UTC),
        content="AI startup funding and venture platform growth.",
        entities=["OpenAI"],
        tags=["security"],
        dedupe_hash=f"dashboard-doc-{unique}",
    )
