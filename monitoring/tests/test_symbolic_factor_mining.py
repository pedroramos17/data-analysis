"""Tests for Sourceflow symbolic factor mining."""

from datetime import timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from monitoring.models import (
    AlertFeedback,
    AlertHit,
    AlertRule,
    DocumentTopic,
    NormalizedDocument,
    RawEvent,
    Source,
    TopicCluster,
)


class SymbolicFactorMiningTests(TestCase):
    """End-to-end tests for the low-cost symbolic factor subsystem."""

    def test_seed_factor_registry_and_dag_are_persisted(self) -> None:
        """Seed registration stores formulas and dependencies in SQLite."""
        from sourceflow.intelligence.factor_base.registry import FactorRegistry
        from sourceflow.intelligence.seeds import seed_factor_definitions

        registry = FactorRegistry(connection)
        registry.ensure_schema()

        registered_count = registry.register_factors(seed_factor_definitions())
        factor = registry.get_factor("amplified_conflict_risk")
        dependencies = registry.factor_dependencies("amplified_conflict_risk")

        self.assertGreaterEqual(registered_count, 18)
        self.assertEqual(factor.name, "amplified_conflict_risk")
        self.assertIn("event_conflict_risk", dependencies)

    def test_parquet_storage_round_trips_factor_values(self) -> None:
        """Computed factor values are persisted outside SQLite as Parquet."""
        from sourceflow.intelligence.factor_base.storage import FactorValueStorage

        with TemporaryDirectory() as directory:
            storage = FactorValueStorage(Path(directory))
            written = storage.write_values("coverage_intensity", _factor_rows())
            read_back = storage.read_values(written)

        self.assertEqual(len(read_back), 2)
        self.assertEqual(read_back[0]["factor_name"], "coverage_intensity")
        self.assertEqual(read_back[1]["entity_id"], "source:2|event:1")

    def test_validator_rejects_type_errors_and_leakage(self) -> None:
        """Formula validation rejects bad types and future-looking operands."""
        from sourceflow.intelligence.search.constraints import SearchConstraints
        from sourceflow.intelligence.symbolic.expression import call, const, operand
        from sourceflow.intelligence.symbolic.validator import validate_formula

        constraints = SearchConstraints(max_depth=4, max_operators=5)
        bad_type = call("js_divergence", operand("article_count"), const(1))
        leaked = call("future_event_growth", operand("article_count"))

        self.assertFalse(validate_formula(bad_type, constraints).is_valid)
        self.assertFalse(validate_formula(leaked, constraints).is_valid)

    def test_factor_dag_orders_dependencies_before_dependents(self) -> None:
        """Dependency scheduling topologically orders factor computation."""
        from sourceflow.intelligence.factor_base.dag import schedule_factor_computation
        from sourceflow.intelligence.seeds import seed_factor_definitions

        scheduled = schedule_factor_computation(seed_factor_definitions())
        names = [factor.name for factor in scheduled]

        self.assertLess(
            names.index("event_conflict_risk"),
            names.index("amplified_conflict_risk"),
        )

    def test_compute_seed_factors_for_historical_events(self) -> None:
        """Seed formulas compute historical values using only available rows."""
        from sourceflow.intelligence.factor_base.registry import FactorRegistry
        from sourceflow.intelligence.factor_base.storage import FactorValueStorage
        from sourceflow.intelligence.runtime import compute_seed_factor_values

        cluster = _event_fixture()
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with override_settings(PARQUET_EXPORT_DIR=output_dir):
                registry = FactorRegistry(connection)
                registry.ensure_schema()
                results = compute_seed_factor_values(
                    connection=connection,
                    output_dir=output_dir,
                    as_of=timezone.now(),
                    history_start=cluster.window_start,
                    history_end=cluster.window_end,
                )
                values = FactorValueStorage(output_dir / "factors").read_values(
                    results["coverage_intensity"]
                )

        self.assertIn("coverage_intensity", results)
        self.assertTrue(
            any(row["factor_name"] == "coverage_intensity" for row in values)
        )

    def test_random_search_generates_500_valid_formulas(self) -> None:
        """Grammar-constrained search can generate a large valid candidate set."""
        from sourceflow.intelligence.search.constraints import SearchConstraints
        from sourceflow.intelligence.search.random_search import (
            generate_random_formulas,
        )
        from sourceflow.intelligence.symbolic.validator import validate_formula

        constraints = SearchConstraints(max_depth=3, max_operators=4)
        formulas = generate_random_formulas(500, constraints, seed=7)

        self.assertEqual(len(formulas), 500)
        self.assertTrue(
            all(validate_formula(item, constraints).is_valid for item in formulas)
        )

    def test_forward_validation_redundancy_and_xai_workflows(self) -> None:
        """Evaluation and explanations score comparison usefulness only."""
        from sourceflow.intelligence.evaluation.forward_validation import (
            evaluate_forward_window,
        )
        from sourceflow.intelligence.evaluation.redundancy import (
            find_redundant_factors,
        )
        from sourceflow.intelligence.evaluation.stability import stability_score
        from sourceflow.intelligence.xai.explain_factor import explain_factor

        rows = _evaluation_rows()
        result = evaluate_forward_window(rows, "future_event_growth", 0.5)
        redundant = find_redundant_factors(rows, threshold=0.95)
        stability = stability_score(rows, "coverage_intensity")
        explanation = explain_factor("coverage_intensity")

        self.assertGreater(result.utility, 0)
        self.assertIn(("coverage_intensity", "copy_intensity"), redundant)
        self.assertGreaterEqual(stability, 0)
        self.assertIn("compares coverage", explanation.lower())

    def test_management_commands_register_compute_search_and_evaluate(self) -> None:
        """Django commands expose the symbolic factor workflows."""
        cluster = _event_fixture()
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with override_settings(PARQUET_EXPORT_DIR=output_dir):
                register_output = StringIO()
                compute_output = StringIO()
                search_output = StringIO()
                evaluate_output = StringIO()

                call_command("register_symbolic_factors", stdout=register_output)
                call_command(
                    "compute_symbolic_factors",
                    as_of=timezone.now().isoformat(),
                    history_start=cluster.window_start.isoformat(),
                    history_end=cluster.window_end.isoformat(),
                    stdout=compute_output,
                )
                call_command("search_symbolic_factors", count=500, stdout=search_output)
                call_command(
                    "evaluate_symbolic_factors",
                    objective="future_event_growth",
                    stdout=evaluate_output,
                )

        self.assertIn("Registered", register_output.getvalue())
        self.assertIn("Computed", compute_output.getvalue())
        self.assertIn("Generated 500", search_output.getvalue())
        self.assertIn("Evaluated", evaluate_output.getvalue())


def _factor_rows() -> list[dict[str, object]]:
    now = timezone.now()
    return [
        _factor_row("source:1|event:1", 1.5, now),
        _factor_row("source:2|event:1", 0.5, now),
    ]


def _factor_row(entity_id: str, value: float, as_of: object) -> dict[str, object]:
    return {
        "factor_name": "coverage_intensity",
        "entity_id": entity_id,
        "event_id": 1,
        "source_id": 1,
        "as_of": as_of,
        "value": value,
    }


def _event_fixture() -> TopicCluster:
    first_source = _source("Source Alpha", "Provider A", "Owner A")
    second_source = _source("Source Beta", "Provider A", "Owner A")
    third_source = _source("Source Gamma", "Provider B", "Owner B")
    first_doc = _document(first_source, "Frame risk claim", ["OpenAI"], ["risk"])
    second_doc = _document(second_source, "Frame risk claim", ["OpenAI"], ["risk"])
    third_doc = _document(third_source, "Frame policy claim", ["OpenAI"], ["policy"])
    cluster = _cluster()
    _attach(cluster, first_doc, DocumentTopic.Role.REPRESENTATIVE)
    _attach(cluster, second_doc, DocumentTopic.Role.EVIDENCE)
    _attach(cluster, third_doc, DocumentTopic.Role.CONTRADICTION)
    alert = _alert(cluster, first_doc)
    AlertFeedback.objects.create(alert_hit=alert, label=AlertFeedback.Label.USEFUL)
    return cluster


def _source(name: str, provider: str, owner: str) -> Source:
    return Source.objects.create(
        name=name,
        url=f"https://example.org/{name}.xml",
        source_type=Source.SourceType.RSS,
        fetch_method=Source.FetchMethod.HTTP,
        category=Source.Category.SECURITY,
        language="en",
        country="US",
        state_affiliation=owner,
        query_template=provider,
        tags=["security"],
    )


def _document(
    source: Source,
    title: str,
    entities: list[str],
    frames: list[str],
) -> NormalizedDocument:
    raw_event = RawEvent.objects.create(
        source=source,
        url=f"https://example.org/raw-{RawEvent.objects.count()}",
        content_hash=f"raw-symbolic-{RawEvent.objects.count()}",
        payload_text="{}",
    )
    return NormalizedDocument.objects.create(
        source=source,
        raw_event=raw_event,
        canonical_url=raw_event.url,
        title=title,
        content=f"{title}. Evidence says conflict and growth may change.",
        text=f"{title}. Evidence says conflict and growth may change.",
        entities=entities,
        tags=["security"],
        metadata={"provider": source.name.rsplit(" ", 1)[0], "frames": frames},
        published_at=timezone.now() - timedelta(hours=1),
        dedupe_hash=f"symbolic-doc-{raw_event.id}",
    )


def _cluster() -> TopicCluster:
    now = timezone.now()
    return TopicCluster.objects.create(
        label="symbolic / conflict / risk",
        canonical_title="Symbolic conflict risk",
        summary="Sources compare claims and frames.",
        topic_label="symbolic",
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


def _alert(cluster: TopicCluster, document: NormalizedDocument) -> AlertHit:
    rule = AlertRule.objects.create(name="Symbolic", rule_type="keyword", query="risk")
    return AlertHit.objects.create(
        rule=rule,
        cluster=cluster,
        document=document,
        source=document.source,
        title="Symbolic alert",
        severity=AlertRule.Severity.MEDIUM,
        dedupe_hash=f"symbolic-alert-{cluster.id}",
        dedupe_key=f"symbolic-alert-{cluster.id}",
        occurred_at=timezone.now(),
    )


def _evaluation_rows() -> list[dict[str, object]]:
    now = timezone.now()
    return [
        _evaluation_row("a", 0.9, 0.91, 1.0, now),
        _evaluation_row("b", 0.2, 0.21, 0.0, now + timedelta(hours=1)),
        _evaluation_row("c", 0.8, 0.79, 1.0, now + timedelta(hours=2)),
    ]


def _evaluation_row(
    entity_id: str,
    coverage_value: float,
    copy_value: float,
    objective_value: float,
    as_of: object,
) -> dict[str, object]:
    return {
        "entity_id": entity_id,
        "as_of": as_of,
        "coverage_intensity": coverage_value,
        "copy_intensity": copy_value,
        "future_event_growth": objective_value,
    }
