"""Tests for Sourceflow symbolic factor mining MVP 2-5 behavior."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
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
from sourceflow.intelligence.search.constraints import SearchConstraints
from sourceflow.intelligence.symbolic.expression import (
    binary,
    call,
    const,
    distribution_op,
    factor,
    graph_op,
    group_op,
    operand,
    post_process,
    time_series,
    unary,
)
from sourceflow.intelligence.symbolic.types import ReturnType


class SymbolicFactorMiningMvpTwoToFiveTests(TestCase):
    """Regression tests for the integrated symbolic mining subsystem."""

    def test_expression_nodes_round_trip_and_render_infix_text(self) -> None:
        """Explicit expression node types serialize and deserialize safely."""
        from sourceflow.intelligence.symbolic.serializer import (
            deserialize_formula,
            formula_text,
            serialize_formula,
        )

        expression = post_process(
            "rank",
            group_op(
                "group_mean",
                time_series("ts_mean", unary("log1p", operand("article_count")), "24h"),
                "provider",
            ),
        )

        payload = serialize_formula(expression)
        restored = deserialize_formula(payload)

        self.assertEqual(payload["kind"], "post_process")
        self.assertEqual(
            formula_text(restored),
            "rank(group_mean(ts_mean(log1p(article_count), 24h), provider))",
        )

    def test_validator_accepts_typed_formulas_and_rejects_invalid_examples(
        self,
    ) -> None:
        """Typed validation rejects distribution, graph, and leakage misuse."""
        from sourceflow.intelligence.symbolic.validator import validate_formula

        constraints = SearchConstraints(max_depth=6, max_operators=12)
        valid = distribution_op(
            "js_divergence",
            operand("frame_distribution", ReturnType.DISTRIBUTION),
            operand("event_frame_distribution", ReturnType.DISTRIBUTION),
        )
        invalid = (
            time_series(
                "ts_mean", operand("frame_distribution", ReturnType.DISTRIBUTION), "24h"
            ),
            time_series("ts_mean", operand("article_count"), "-1h"),
            distribution_op(
                "js_divergence", operand("article_count"), operand("event_source_count")
            ),
            graph_op("graph_pagerank", operand("article_count")),
            binary(
                "add",
                operand("frame_distribution", ReturnType.DISTRIBUTION),
                operand("article_count"),
            ),
            operand("unknown_operand"),
            operand("future_event_growth"),
        )

        self.assertTrue(validate_formula(valid, constraints).is_valid)
        self.assertTrue(
            all(not validate_formula(item, constraints).is_valid for item in invalid)
        )

    def test_compiler_executes_group_time_series_post_process_and_factor_operands(
        self,
    ) -> None:
        """Compiled formulas use raw operands and loaded factor values."""
        from sourceflow.intelligence.symbolic.compiler import (
            FactorExecutionContext,
            compile_formula,
        )

        frame = _execution_frame()
        same_event = _same_event_frame(frame)
        with TemporaryDirectory() as directory:
            storage = FactorValueStorage(Path(directory) / "factors")
            storage.write_values("coverage_intensity", _factor_rows())
            context = FactorExecutionContext(
                as_of=timezone.now(),
                history_start=timezone.now() - timedelta(days=1),
                history_end=timezone.now(),
                factor_storage=storage,
            )
            expression = binary(
                "add",
                factor("coverage_intensity"),
                group_op("group_mean", operand("article_count"), "event_id"),
            )
            plan = compile_formula("candidate_factor", expression, context=context)
            values = plan.execute(frame)
            legacy_plan = compile_formula(
                "legacy_group",
                call("group_mean", operand("article_count")),
                context=context,
            )
            legacy_values = legacy_plan.execute(same_event)

        self.assertEqual(round(float(values.iloc[0]), 3), 3.5)
        self.assertEqual(round(float(values.iloc[1]), 3), 4.5)
        self.assertEqual(tuple(legacy_values.round(3)), (3.0, 3.0))

    def test_compiler_filters_unavailable_rows_and_numeric_special_types(self) -> None:
        """Compiled formulas avoid future rows and return numeric special outputs."""
        from sourceflow.intelligence.symbolic.compiler import (
            FactorExecutionContext,
            compile_formula,
        )

        frame = _execution_frame()
        future = frame.iloc[[0]].copy()
        future["entity_id"] = ["event:future"]
        future["available_at"] = [timezone.now() + timedelta(days=1)]
        mixed = pd.concat([frame, future], ignore_index=True)
        context = FactorExecutionContext.from_frame(mixed, _storage_dir())
        distribution = distribution_op(
            "js_divergence",
            operand("frame_distribution", ReturnType.DISTRIBUTION),
            operand("event_frame_distribution", ReturnType.DISTRIBUTION),
        )
        graph = graph_op(
            "graph_pagerank", operand("entity_node", ReturnType.GRAPH_NODE)
        )
        mixed["frame_distribution"] = [{"risk": 1}, {"risk": 2}, {"risk": 1}]
        mixed["event_frame_distribution"] = [{"risk": 1}, {"policy": 1}, {"risk": 1}]
        mixed["entity_node"] = ["entity:a", "entity:b", "entity:c"]

        distribution_values = compile_formula(
            "distribution_candidate", distribution, context=context
        ).execute(mixed)
        graph_values = compile_formula(
            "graph_candidate", graph, context=context
        ).execute(mixed)

        self.assertEqual(len(distribution_values), 2)
        self.assertEqual(len(graph_values), 2)
        self.assertTrue(all(isinstance(value, float) for value in distribution_values))
        self.assertGreater(float(distribution_values.iloc[1]), 0)

    def test_registry_upgrades_runs_candidates_and_dag_skip_force(self) -> None:
        """Registry upgrade stores v2 metadata and DAG execution records runs."""
        from sourceflow.intelligence.factor_base.dag import execute_factor_dag
        from sourceflow.intelligence.factor_base.migrations_or_init import (
            upgrade_factor_schema,
        )
        from sourceflow.intelligence.symbolic.compiler import FactorExecutionContext

        registry = FactorRegistry(connection)
        upgrade_factor_schema(connection)
        definition = FactorDefinition(
            "candidate_add",
            "Candidate comparison factor.",
            binary("add", operand("article_count"), const(1)),
            "event",
            status="candidate",
        )
        context = FactorExecutionContext.from_frame(_execution_frame(), _storage_dir())

        registry.register_factor(definition)
        first = execute_factor_dag((definition,), context, force=False)
        second = execute_factor_dag((definition,), context, force=False)
        forced = execute_factor_dag((definition,), context, force=True)

        self.assertEqual(registry.get_factor("candidate_add").status, "candidate")
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(forced), 1)
        self.assertGreaterEqual(len(registry.list_factor_runs("candidate_add")), 2)

    def test_random_search_filters_and_persists_candidate_formulas(self) -> None:
        """Random search evaluates valid candidates and rejects redundant formulas."""
        from sourceflow.intelligence.search.random_search import run_random_search

        context = _search_context()
        constraints = SearchConstraints(max_depth=4, max_operators=12)
        results = run_random_search(
            count=500,
            constraints=constraints,
            context=context,
            objective="future_event_growth",
            seed=7,
        )
        candidates = FactorRegistry(connection).list_factors(status="candidate")

        self.assertEqual(results.generated_count, 500)
        self.assertGreater(results.accepted_count, 0)
        self.assertTrue(all(item.score.final_score >= 0 for item in results.accepted))
        self.assertTrue(
            any(item.name.startswith("candidate_random_") for item in candidates)
        )

    def test_genetic_programming_preserves_validity_and_persists_results(self) -> None:
        """GP mutation/crossover stay typed and persists candidates."""
        from sourceflow.intelligence.search.crossover import crossover_formulas
        from sourceflow.intelligence.search.genetic_programming import (
            run_genetic_search,
        )
        from sourceflow.intelligence.search.mutation import mutate_formula
        from sourceflow.intelligence.symbolic.validator import validate_formula

        constraints = SearchConstraints(max_depth=5, max_operators=12)
        left = binary("add", operand("article_count"), operand("event_source_count"))
        right = unary("log1p", operand("evidence_span_count"))
        rng = random.Random(9)
        mutated = mutate_formula(left, constraints, rng)
        child = crossover_formulas(left, right, constraints, rng)
        result = run_genetic_search(
            population_size=20,
            generations=5,
            constraints=constraints,
            context=_search_context(),
            objective="future_claim_conflict",
            seed=9,
        )

        self.assertTrue(validate_formula(mutated, constraints).is_valid)
        self.assertTrue(validate_formula(child, constraints).is_valid)
        self.assertEqual(result.generations_completed, 5)
        self.assertGreaterEqual(result.best_scores[-1], result.best_scores[0])

    def test_xai_and_graphrag_context_use_neutral_explainable_language(self) -> None:
        """GraphRAG context includes event evidence and neutral factor explanations."""
        from sourceflow.intelligence.xai.explain_factor import explain_factor_score
        from sourceflow.intelligence.xai.rag_context import build_event_rag_context

        cluster = _event_fixture()
        output_dir = _storage_dir()
        explanation = explain_factor_score(
            factor_name="amplified_conflict_risk",
            expression_text="event_conflict_risk * provider_amplification",
            score=0.91,
            operands={"event_conflict_risk": 0.91, "provider_amplification": 0.84},
            dependencies=("event_conflict_risk", "provider_amplification"),
        )
        context = build_event_rag_context(cluster.id, output_dir)

        self.assertIn("This does not mean", explanation.summary)
        self.assertNotIn("fake news", explanation.summary.lower())
        self.assertEqual(context.event_id, cluster.id)
        self.assertTrue(context.top_articles)
        self.assertTrue(context.top_sources)
        self.assertTrue(
            (output_dir / "graphrag_context" / "events" / f"{cluster.id}.json").exists()
        )

    def test_canonical_management_commands_cover_mvp_two_to_five(self) -> None:
        """Canonical commands cover MVP 2-5 workflows."""
        cluster = _event_fixture()
        with TemporaryDirectory() as directory:
            with override_settings(
                GRAPHRAG_CONTEXT_DIR=Path(directory),
                PARQUET_EXPORT_DIR=Path(directory),
            ):
                call_command("init_factor_base")
                call_command("register_seed_factors")
                call_command("compute_factors", as_of=timezone.now().isoformat())
                call_command("search_symbolic_factors", method="random", n=20, seed=3)
                _write_labeled_factor_values(Path(directory))
                call_command("evaluate_factors", factor="coverage_intensity")
                call_command(
                    "explain_factor_score",
                    factor="coverage_intensity",
                    entity_id="event:1",
                )
                call_command("build_graphrag_context", event_id=cluster.id)

        self.assertGreater(FactorRegistry(connection).summary().evaluation_count, 0)


def _execution_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entity_id": ["event:1", "event:2"],
            "event_id": [1, 2],
            "source_id": [10, 11],
            "provider": ["Provider A", "Provider B"],
            "as_of": [timezone.now(), timezone.now() + timedelta(hours=1)],
            "available_at": [timezone.now(), timezone.now()],
            "article_count": [2.0, 4.0],
            "event_source_count": [3.0, 5.0],
            "evidence_span_count": [1.0, 2.0],
            "future_event_growth": [1.0, 0.0],
            "future_claim_conflict": [0.0, 1.0],
        }
    )


def _same_event_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["event_id"] = [1, 1]
    return frame


def _factor_rows() -> list[dict[str, object]]:
    return [
        {"factor_name": "coverage_intensity", "entity_id": "event:1", "value": 1.5},
        {"factor_name": "coverage_intensity", "entity_id": "event:2", "value": 0.5},
    ]


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
            },
            {
                "factor_name": "coverage_intensity",
                "entity_id": "event:2",
                "as_of": timezone.now().isoformat(),
                "value": 0.2,
                "future_event_growth": 0.0,
            },
        ],
    )


def _search_context() -> object:
    from sourceflow.intelligence.symbolic.compiler import FactorExecutionContext

    return FactorExecutionContext.from_frame(_execution_frame(), _storage_dir())


def _storage_dir() -> Path:
    directory = Path(TemporaryDirectory().name)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _event_fixture() -> TopicCluster:
    documents = [
        _document(_source("MVP Alpha"), "Frame risk claim", ["risk"]),
        _document(_source("MVP Beta"), "Frame risk claim", ["risk"]),
        _document(_source("MVP Gamma"), "Frame policy claim", ["policy"]),
    ]
    cluster = _cluster()
    for role, document in zip(_roles(), documents, strict=True):
        _attach(cluster, document, role)
    return cluster


def _roles() -> tuple[str, str, str]:
    return (
        DocumentTopic.Role.REPRESENTATIVE,
        DocumentTopic.Role.EVIDENCE,
        DocumentTopic.Role.CONTRADICTION,
    )


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
        content_hash=f"raw-mvp-{RawEvent.objects.count()}",
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
        dedupe_hash=f"mvp-doc-{raw_event.id}",
    )


def _cluster() -> TopicCluster:
    now = timezone.now()
    return TopicCluster.objects.create(
        label=f"mvp symbolic {datetime.utcnow().timestamp()}",
        canonical_title="MVP symbolic event",
        summary="Sources compare claims and frames.",
        topic_label="mvp",
        window_start=now - timedelta(hours=24),
        window_end=now,
        keywords=["claim", "risk", "policy"],
        entities=["OpenAI"],
        document_count=3,
        source_count=3,
        score=0.7,
        novelty_score=0.6,
        trend_score=0.5,
        severity_score=0.4,
        confidence_score=0.8,
    )


def _attach(cluster: TopicCluster, document: NormalizedDocument, role: str) -> None:
    DocumentTopic.objects.create(
        cluster=cluster,
        document=document,
        overlap_score=0.9,
        similarity=0.9,
        role=role,
    )
