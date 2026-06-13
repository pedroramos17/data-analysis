"""Phase 8 dependency-light source comparison tests."""

from __future__ import annotations

import unittest
from decimal import Decimal

from sourceflow.analysis.source_bias import CoverageSignal, analyze_source_bias, group_sources
from sourceflow.claims.comparison import compare_event_cluster_claims
from sourceflow.events.clustering import EventCluster, cluster_events, event_cluster_key


class Phase8SourceComparisonUtilityTests(unittest.TestCase):
    def test_group_sources_by_owner_region_category_and_type(self) -> None:
        sources = [
            {
                "id": "1",
                "name": "Outlet A",
                "owner": "Wire Co",
                "country": "BR",
                "bias_tags": ["Business"],
                "source_type": "rss",
                "reliability_score": "0.80",
            },
            {
                "id": "2",
                "name": "Outlet B",
                "owner": "Wire Co",
                "country": "BR",
                "bias_tags": ["Business"],
                "source_type": "html",
                "reliability_score": "0.60",
            },
        ]

        groups = group_sources(sources, by=("owner",))

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].key.owner, "wire_co")
        self.assertEqual(groups[0].reliability_score, Decimal("0.70"))

    def test_cluster_events_groups_same_actor_type_and_object(self) -> None:
        events = [
            {"id": "1", "actor_id": "42", "event_type": "lawsuit", "object_literal": "lawsuit"},
            {"id": "2", "actor_id": "42", "event_type": "lawsuit", "object_literal": "lawsuit"},
        ]

        clusters = cluster_events(events)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(event_cluster_key(events[0]), event_cluster_key(events[1]))
        self.assertEqual(len(clusters[0].events), 2)

    def test_compare_event_cluster_outputs_partial_cwa_omission(self) -> None:
        source_a = {"id": "1", "name": "Outlet A", "owner": "Wire Co", "source_type": "rss"}
        source_b = {"id": "2", "name": "Outlet B", "owner": "Regional Co", "source_type": "rss"}
        claim = {
            "id": "claim-1",
            "subject_id": "42",
            "predicate": "faces",
            "object_literal": "lawsuit",
            "polarity": "negative",
            "source": source_a,
            "source_id": "1",
            "document_id": "doc-1",
            "evidence_span_id": "ev-1",
        }
        cluster = EventCluster(
            cluster_id="cluster-1",
            key="actor:42|type:lawsuit|object:literal:lawsuit",
            events=(
                {"id": "event-1", "source": source_a, "document_id": "doc-1"},
                {"id": "event-2", "source": source_b, "document_id": "doc-2"},
            ),
            claims=(claim,),
        )

        comparison = compare_event_cluster_claims(
            cluster,
            expected_sources=[source_a, source_b],
            group_by=("owner",),
        )

        self.assertEqual(comparison.assumption_policy, "PartialCWA")
        self.assertEqual(len(comparison.summaries), 2)
        omissions = comparison.omissions
        self.assertEqual(len(omissions), 1)
        self.assertIn("source omitted", omissions[0].description)
        self.assertFalse(omissions[0].inferred_false)
        self.assertEqual(omissions[0].assumption_policy, "PartialCWA")

    def test_bias_detection_flags_amplification_and_sentiment_shift(self) -> None:
        findings = analyze_source_bias(
            [
                CoverageSignal(
                    group_key=group_sources([{"id": "1", "name": "A", "owner": "Owner A"}])[0].key,
                    article_count=3,
                    claim_count=4,
                    claim_frequency={"claim:x": 4},
                    polarity_counts={"negative": 4},
                ),
                CoverageSignal(
                    group_key=group_sources([{"id": "2", "name": "B", "owner": "Owner B"}])[0].key,
                    article_count=1,
                    claim_count=1,
                    claim_frequency={"claim:y": 1},
                    polarity_counts={"positive": 1},
                ),
            ]
        )

        detection_types = {finding.detection_type for finding in findings}
        self.assertIn("provider_amplification", detection_types)
        self.assertIn("sentiment_shift", detection_types)


if __name__ == "__main__":
    unittest.main()
