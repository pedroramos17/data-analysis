"""Quant4 graph and topology lab tests."""

from __future__ import annotations

import json
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase, override_settings


class Quant4GraphBuilderTests(TestCase):
    """Graph builders must stay leakage-safe and persist reusable snapshots."""

    def test_graph_edges_use_only_window_data_up_to_window_end(self) -> None:
        """Future observations cannot change correlation graph edges."""
        from quant4.services.graphs.graph_builders import CorrelationGraphBuilder

        result = CorrelationGraphBuilder(min_abs_weight=0.1).build(
            {
                "AAA": [
                    (date(2024, 1, 1), 1.0),
                    (date(2024, 1, 2), 2.0),
                    (date(2024, 1, 3), 3.0),
                ],
                "BBB": [
                    (date(2024, 1, 1), 10.0),
                    (date(2024, 1, 2), 20.0),
                    (date(2024, 1, 3), -30.0),
                ],
            },
            window_end=date(2024, 1, 2),
        )

        self.assertEqual(result.metadata["max_observation_date"], "2024-01-02")
        self.assertGreater(result.edges[0]["weight"], 0.9)

    def test_graph_snapshot_writes_node_edge_and_adjacency_paths(self) -> None:
        """Snapshot persistence writes reusable graph artifact paths."""
        from quant4.models import GraphSnapshot
        from quant4.services.graphs.graph_builders import CorrelationGraphBuilder
        from quant4.services.graphs.graph_sampling import persist_graph_snapshot

        result = CorrelationGraphBuilder(min_abs_weight=0.1).build(
            {
                "AAA": [(date(2024, 1, 1), 1.0), (date(2024, 1, 2), 2.0)],
                "BBB": [(date(2024, 1, 1), 1.0), (date(2024, 1, 2), 3.0)],
            },
            window_end=date(2024, 1, 2),
        )

        with TemporaryDirectory() as output_dir:
            snapshot = persist_graph_snapshot(
                name="graph-smoke",
                result=result,
                output_dir=output_dir,
                data_range=(date(2024, 1, 1), date(2024, 1, 2)),
                split_range=(date(2024, 1, 2), date(2024, 1, 2)),
            )
            stored = GraphSnapshot.objects.get(pk=snapshot.pk)
            node_payload = json.loads(
                Path(stored.node_path).read_text(encoding="utf-8")
            )

        self.assertEqual(stored.node_count, 2)
        self.assertTrue(stored.edge_path.endswith("edges.json"))
        self.assertTrue(stored.adjacency_path.endswith("adjacency.json"))
        self.assertEqual(node_payload["nodes"], ["AAA", "BBB"])

    @override_settings(
        SOURCEFLOW_FEATURE_FLAGS={"QUANT4_SOURCEFLOW_KNOWLEDGE_GRAPH": False}
    )
    def test_sourceflow_knowledge_graph_builder_is_behind_feature_flag(self) -> None:
        """Sourceflow adapter requires an explicit feature flag."""
        from quant4.services.graphs.graph_builders import NewsKnowledgeGraphBuilder
        from sourceflow.config.feature_flags import FeatureDisabledError

        with self.assertRaisesRegex(FeatureDisabledError, "SOURCEFLOW"):
            NewsKnowledgeGraphBuilder().build([], [])

    def test_quant4_build_graphs_command_persists_snapshot_paths(self) -> None:
        """The command persists a reusable GraphSnapshot artifact set."""
        from quant4.models import GraphSnapshot

        with TemporaryDirectory() as output_dir:
            call_command(
                "quant4_build_graphs",
                "--name",
                "command-graph",
                "--series-json",
                json.dumps(
                    {
                        "AAA": [["2024-01-01", 1], ["2024-01-02", 2]],
                        "BBB": [["2024-01-01", 1], ["2024-01-02", 3]],
                    }
                ),
                "--window-end",
                "2024-01-02",
                "--output-dir",
                output_dir,
                stdout=StringIO(),
            )
            snapshot = GraphSnapshot.objects.get(name="command-graph")

        self.assertTrue(snapshot.node_path.endswith("nodes.json"))
        self.assertEqual(snapshot.metrics_json["builder"], "correlation")


class Quant4TopologyTests(TestCase):
    """Topology helpers expose validation priors without overclaiming."""

    def test_hypergraph_builder_creates_metadata_groups(self) -> None:
        """Sector, index, and regime metadata create hyperedges."""
        from quant4.services.graphs.hypergraphs import HypergraphBuilder

        hypergraph = HypergraphBuilder().build(
            {
                "AAA": {"sector": "Technology", "index": "SPX", "regime": "calm"},
                "BBB": {"sector": "Technology", "index": "SPX", "regime": "calm"},
                "CCC": {"sector": "Energy", "index": "SPX", "regime": "stress"},
            }
        )

        self.assertIn("sector:Technology", hypergraph.hyperedges)
        self.assertIn("index:SPX", hypergraph.hyperedges)
        self.assertIn("regime:calm", hypergraph.hyperedges)

    def test_optional_graph_dependencies_fail_clearly(self) -> None:
        """Optional graph filters identify missing dependencies."""
        from quant4.services.graphs.graph_filters import PMFGFilter
        from quant4.services.registry import OptionalDependencyMissingError

        with self.assertRaisesRegex(OptionalDependencyMissingError, "pmfg"):
            PMFGFilter().filter_edges([])
