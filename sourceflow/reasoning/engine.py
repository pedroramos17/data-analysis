"""Django-backed inference engine for rule-derived beliefs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from sourceflow.reasoning.contradictions import support_is_disputed
from sourceflow.reasoning.rules import RuleAction, RuleDefinition, load_rule_definitions
from sourceflow.tms import JustificationSpec, create_belief, ensure_assumption_policy


class InferenceEngineError(ValueError):
    """Raised for invalid inference engine inputs."""


@dataclass(frozen=True)
class InferenceResult:
    """One rule evaluation outcome."""

    rule_id: str
    status: str
    reason: str
    belief: object | None = None
    rule: object | None = None
    support: object | None = None


class InferenceEngine:
    """Apply persisted or file-backed rules to canonical support records."""

    def __init__(self, rules: Iterable[RuleDefinition]) -> None:
        self.rules = list(rules)

    @classmethod
    def from_rule_files(cls, paths: Iterable[str | Path]) -> "InferenceEngine":
        """Build an engine from YAML rule files or directories."""
        return cls(load_rule_definitions(list(paths)))

    @classmethod
    def from_default_rules(cls, directory: str | Path = "rules") -> "InferenceEngine":
        """Build an engine from the project default rule directory."""
        return cls.from_rule_files([directory])

    def upsert_rules(self) -> list[object]:
        """Persist current rule definitions as active `InferenceRule` rows."""
        return [upsert_inference_rule(definition) for definition in self.rules]

    def infer_from_event(self, event: object) -> list[InferenceResult]:
        """Apply all matching rules to one event support record."""
        return self.infer_from_support(event)

    def infer_from_events(self, events: Iterable[object]) -> list[InferenceResult]:
        """Apply all matching rules to many event support records."""
        results: list[InferenceResult] = []
        for event in events:
            results.extend(self.infer_from_event(event))
        return results

    def infer_from_support(self, support: object) -> list[InferenceResult]:
        """Apply matching rules to a claim, event, or belief support record."""
        results: list[InferenceResult] = []
        for definition in self.rules:
            if not definition.matches(support):
                continue
            rule = upsert_inference_rule(definition)
            if support_is_disputed(support):
                results.append(
                    InferenceResult(
                        rule_id=definition.rule_id,
                        status="skipped_contradicted_support",
                        reason="support is source-disputed; hard truth derivation skipped",
                        rule=rule,
                        support=support,
                    )
                )
                continue
            if definition.blocked_by_exception(support):
                results.append(
                    InferenceResult(
                        rule_id=definition.rule_id,
                        status="blocked_by_exception",
                        reason="rule exception matched support",
                        rule=rule,
                        support=support,
                    )
                )
                continue
            for action in definition.then:
                results.append(self._create_belief(definition, action, support, rule))
        return results

    def _create_belief(
        self,
        definition: RuleDefinition,
        action: RuleAction,
        support: object,
        rule: object,
    ) -> InferenceResult:
        provenance = _belief_provenance(definition, support)
        belief = create_belief(
            belief_type=action.belief_type,
            predicate=action.predicate,
            subject_entity=_subject_entity(support),
            object_literal=action.object_literal,
            justifications=[
                _support_justification(
                    support,
                    rule=rule,
                    weight=_support_weight(definition, support),
                )
            ],
            provenance=provenance,
            created_by_rule=rule,
            policy_code=definition.assumption_policy or "OWA",
        )
        belief.metadata_json = {
            **dict(getattr(belief, "metadata_json", {}) or {}),
            **dict(action.metadata),
            "rule_id": definition.rule_id,
        }
        belief.save(update_fields=["metadata_json", "updated_at"])
        return InferenceResult(
            rule_id=definition.rule_id,
            status="created",
            reason="belief created",
            belief=belief,
            rule=rule,
            support=support,
        )


def upsert_inference_rule(definition: RuleDefinition) -> object:
    """Persist or update one inference rule definition."""
    from sourceflow.models import InferenceRule

    policy = ensure_assumption_policy(definition.assumption_policy) if definition.assumption_policy else None
    rule, _created = InferenceRule.objects.update_or_create(
        rule_id=definition.rule_id,
        defaults={
            "name": definition.name or definition.rule_id,
            "rule_type": definition.rule_type,
            "definition_json": definition.to_mapping(),
            "confidence_delta": definition.confidence_delta,
            "assumption_policy": policy,
            "is_active": definition.is_active,
            "provenance_json": {
                "created_by": "sourceflow.reasoning.engine",
                "rule_id": definition.rule_id,
            },
        },
    )
    return rule


def _support_justification(support: object, *, rule: object, weight: Decimal) -> JustificationSpec:
    from sourceflow.models import Belief, Claim, Event, Justification

    if isinstance(support, Event):
        return JustificationSpec(Justification.SupportType.DERIVED_BY_RULE, event=support, rule=rule, weight=weight)
    if isinstance(support, Claim):
        return JustificationSpec(Justification.SupportType.DERIVED_BY_RULE, claim=support, rule=rule, weight=weight)
    if isinstance(support, Belief):
        return JustificationSpec(Justification.SupportType.DERIVED_BY_RULE, belief=support, rule=rule, weight=weight)
    raise InferenceEngineError(f"unsupported support type: {type(support).__name__}")


def _support_weight(definition: RuleDefinition, support: object) -> Decimal:
    if definition.rule_type == "deductive":
        return Decimal("1")
    confidence = Decimal(str(getattr(support, "confidence", Decimal("1")) or 0))
    return min(Decimal("1"), max(Decimal("0"), confidence + definition.confidence_delta))


def _subject_entity(support: object) -> object | None:
    return getattr(support, "actor_entity", None) or getattr(support, "subject_entity", None)


def _belief_provenance(definition: RuleDefinition, support: object) -> dict[str, object]:
    return {
        "created_by": "sourceflow.reasoning.engine",
        "rule_id": definition.rule_id,
        "rule_type": definition.rule_type,
        "support_type": type(support).__name__,
        "support_id": str(getattr(support, "pk", "")),
        "source_id": getattr(support, "source_id", None),
        "document_id": getattr(support, "document_id", None),
        "evidence_span_id": getattr(support, "evidence_span_id", None),
    }
