"""Tests for the Sourceflow intelligence operator UI."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from monitoring.models import (
    DocumentTopic,
    NormalizedDocument,
    RawEvent,
    Source,
    TopicCluster,
)
from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.factor_base.storage import FactorValueStorage
from sourceflow.intelligence.factor_base.types import FactorDefinition


class IntelligenceUiTests(TestCase):
    """Browser-facing tests for the symbolic factor UI."""

    def test_intelligence_dashboard_renders_and_nav_links(self) -> None:
        """The dashboard and global nav expose the intelligence UI."""
        response = self.client.get(reverse("monitoring:intelligence-dashboard"))

        self.assertContains(response, "Sourceflow Intelligence")
        self.assertContains(response, "comparison/propagation")
        self.assertContains(response, reverse("monitoring:intelligence-dashboard"))

    def test_register_action_populates_factor_list(self) -> None:
        """The register POST creates seed factors and redirects to the UI."""
        response = self.client.post(
            reverse("monitoring:intelligence-register-action"),
            follow=True,
        )
        list_response = self.client.get(reverse("monitoring:intelligence-factor-list"))

        self.assertContains(response, "Registered 18 symbolic factors")
        self.assertContains(list_response, "coverage_intensity")
        self.assertContains(list_response, "article_count")

    def test_factor_detail_shows_formula_dependencies_and_explanation(self) -> None:
        """Factor detail exposes formula metadata and XAI explanation."""
        FactorRegistry(connection).register_factors(_seed_definitions())

        response = self.client.get(
            reverse(
                "monitoring:intelligence-factor-detail",
                kwargs={"name": "amplified_conflict_risk"},
            )
        )

        self.assertContains(response, "amplified_conflict_risk")
        self.assertContains(response, "event_conflict_risk")
        self.assertContains(response, "comparison factor")
        self.assertContains(response, "Formula JSON")

    def test_compute_action_writes_values_and_rows_api_filters(self) -> None:
        """Compute writes Parquet artifacts and the rows API previews values."""
        cluster = _event_fixture()
        with TemporaryDirectory() as directory:
            with override_settings(PARQUET_EXPORT_DIR=Path(directory)):
                response = self.client.post(
                    reverse("monitoring:intelligence-compute-action"),
                    data=_compute_form(cluster),
                    follow=True,
                )
                rows_response = self.client.get(
                    reverse(
                        "monitoring:intelligence-factor-rows-api",
                        kwargs={"name": "coverage_intensity"},
                    ),
                    {"page_size": "2", "search": "source:"},
                )

        payload = rows_response.json()
        self.assertContains(response, "Computed 18 symbolic factors")
        self.assertLessEqual(len(payload["rows"]), 2)
        self.assertGreater(payload["total"], 0)
        self.assertIn("value", payload["columns"])

    def test_search_action_generates_formula_preview(self) -> None:
        """Random search stores only a bounded preview in the session."""
        response = self.client.post(
            reverse("monitoring:intelligence-search-action"),
            data={"count": "500", "seed": "7"},
            follow=True,
        )
        preview = self.client.session.get("intelligence_formula_preview", ())

        self.assertContains(response, "Generated 500 valid formulas")
        self.assertEqual(len(preview), 20)
        self.assertContains(response, "Latest Formula Preview")

    def test_evaluate_action_requires_future_objective_labels(self) -> None:
        """Evaluation does not derive future labels from factor values."""
        cluster = _event_fixture()
        with TemporaryDirectory() as directory:
            with override_settings(PARQUET_EXPORT_DIR=Path(directory)):
                self.client.post(
                    reverse("monitoring:intelligence-compute-action"),
                    data=_compute_form(cluster),
                )
                missing_response = self.client.post(
                    reverse("monitoring:intelligence-evaluate-action"),
                    data={
                        "factor": "coverage_intensity",
                        "objective": "future_event_growth",
                    },
                    follow=True,
                )
                _write_labeled_factor_values(Path(directory))
                labeled_response = self.client.post(
                    reverse("monitoring:intelligence-evaluate-action"),
                    data={
                        "factor": "coverage_intensity",
                        "objective": "future_event_growth",
                    },
                    follow=True,
                )

        self.assertContains(missing_response, "No values found for coverage_intensity")
        self.assertContains(labeled_response, "Evaluated coverage_intensity")
        self.assertEqual(FactorRegistry(connection).summary().evaluation_count, 1)


def _seed_definitions() -> tuple[FactorDefinition, ...]:
    from sourceflow.intelligence.seeds import seed_factor_definitions

    return seed_factor_definitions()


def _compute_form(cluster: TopicCluster) -> dict[str, str]:
    return {
        "as_of": cluster.window_end.isoformat(),
        "history_start": cluster.window_start.isoformat(),
        "history_end": cluster.window_end.isoformat(),
    }


def _write_labeled_factor_values(output_dir: Path) -> None:
    storage = FactorValueStorage(output_dir / "factors")
    storage.write_values(
        "coverage_intensity",
        [
            {
                "factor_name": "coverage_intensity",
                "entity_id": "event:1",
                "as_of": timezone.now().isoformat(),
                "value": 0.9,
                "future_event_growth": 1.0,
            }
        ],
    )


def _event_fixture() -> TopicCluster:
    first_doc = _document(_source("Source Alpha"), "Frame risk claim", ["risk"])
    second_doc = _document(_source("Source Beta"), "Frame risk claim", ["risk"])
    third_doc = _document(_source("Source Gamma"), "Frame policy claim", ["policy"])
    cluster = _cluster()
    _attach(cluster, first_doc, DocumentTopic.Role.REPRESENTATIVE)
    _attach(cluster, second_doc, DocumentTopic.Role.EVIDENCE)
    _attach(cluster, third_doc, DocumentTopic.Role.CONTRADICTION)
    return cluster


def _source(name: str) -> Source:
    return Source.objects.create(
        name=name,
        url=f"https://example.org/{name}.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.SECURITY,
        language="en",
        country="US",
        state_affiliation=f"{name} Owner",
        query_template=f"{name} Provider",
        tags=["security"],
    )


def _document(source: Source, title: str, frames: list[str]) -> NormalizedDocument:
    raw_event = RawEvent.objects.create(
        source=source,
        url=f"https://example.org/raw-{RawEvent.objects.count()}",
        content_hash=f"raw-intelligence-{RawEvent.objects.count()}",
        payload_text="{}",
    )
    return NormalizedDocument.objects.create(
        source=source,
        raw_event=raw_event,
        canonical_url=raw_event.url,
        title=title,
        content=f"{title}. Evidence says coverage changed.",
        text=f"{title}. Evidence says coverage changed.",
        entities=["OpenAI"],
        tags=["security"],
        metadata={"provider": source.query_template, "frames": frames},
        published_at=timezone.now() - timedelta(hours=1),
        dedupe_hash=f"intelligence-doc-{raw_event.id}",
    )


def _cluster() -> TopicCluster:
    now = timezone.now()
    return TopicCluster.objects.create(**_cluster_values(now))


def _cluster_values(now: datetime) -> dict[str, object]:
    return {
        "label": "intelligence / symbolic / factors",
        "canonical_title": "Symbolic factor event",
        "summary": "Sources compare claims and frames.",
        "topic_label": "intelligence",
        "window_start": now - timedelta(hours=24),
        "window_end": now,
        "keywords": ["claim", "risk", "policy"],
        "entities": ["OpenAI"],
        "document_count": 3,
        "source_count": 3,
        "score": 0.7,
        "novelty_score": 0.6,
        "trend_score": 0.5,
        "severity_score": 0.4,
        "confidence_score": 0.8,
    }


def _attach(
    cluster: TopicCluster,
    document: NormalizedDocument,
    role: str,
) -> DocumentTopic:
    return DocumentTopic.objects.create(
        cluster=cluster,
        document=document,
        overlap_score=0.9,
        similarity=0.9,
        role=role,
    )
