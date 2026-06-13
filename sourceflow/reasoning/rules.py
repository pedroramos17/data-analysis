"""Dependency-light rule definitions and matching helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

import yaml

RULE_TYPES = frozenset(
    {
        "deductive",
        "default",
        "abductive",
        "diagnostic",
        "risk_propagation",
        "source_comparison",
        "retrieval_expansion",
    }
)

_EXACT_MATCH_FIELDS = frozenset({"event_type", "polarity", "predicate", "rule_type", "status"})
_OBJECT_FIELDS = frozenset({"object", "object_literal"})


class RuleDefinitionError(ValueError):
    """Raised when a rule definition is invalid."""


@dataclass(frozen=True)
class RuleCondition:
    """One AND group of field predicates."""

    criteria: Mapping[str, Any]

    def matches(self, support: object) -> bool:
        """Return whether all criteria match a support object or mapping."""
        return all(value_matches(field_value(support, key), expected, key=key) for key, expected in self.criteria.items())


@dataclass(frozen=True)
class RuleAction:
    """Belief-producing action in a rule consequent."""

    belief_type: str
    predicate: str
    object_literal: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleDefinition:
    """Portable rule definition parsed from YAML or JSON-like mappings."""

    rule_id: str
    rule_type: str
    when: tuple[RuleCondition, ...]
    then: tuple[RuleAction, ...]
    confidence_delta: Decimal = Decimal("0")
    exceptions: tuple[RuleCondition, ...] = ()
    name: str = ""
    assumption_policy: str | None = None
    is_active: bool = True
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "RuleDefinition":
        """Build a validated rule definition from a mapping."""
        rule_id = str(mapping.get("id") or mapping.get("rule_id") or "").strip()
        if not rule_id:
            raise RuleDefinitionError("rule id is required")
        rule_type = str(mapping.get("type") or mapping.get("rule_type") or "deductive").strip()
        if rule_type not in RULE_TYPES:
            raise RuleDefinitionError(f"unsupported rule type: {rule_type!r}")
        when = _parse_conditions(mapping.get("when"), field_name="when")
        then = _parse_actions(mapping.get("then"))
        confidence_delta = _parse_decimal(mapping.get("confidence_delta", "0"), "confidence_delta")
        exceptions = _parse_conditions(mapping.get("exceptions", []), field_name="exceptions", required=False)
        return cls(
            rule_id=rule_id,
            rule_type=rule_type,
            when=when,
            then=then,
            confidence_delta=confidence_delta,
            exceptions=exceptions,
            name=str(mapping.get("name") or rule_id).strip(),
            assumption_policy=mapping.get("assumption_policy"),
            is_active=bool(mapping.get("is_active", True)),
            raw=dict(mapping),
        )

    def matches(self, support: object) -> bool:
        """Return whether the support satisfies the antecedent."""
        return self.is_active and all(condition.matches(support) for condition in self.when)

    def blocked_by_exception(self, support: object) -> bool:
        """Return whether any exception condition blocks the rule."""
        return any(condition.matches(support) for condition in self.exceptions)

    def to_mapping(self) -> dict[str, Any]:
        """Return a JSON-serializable normalized representation."""
        return {
            "id": self.rule_id,
            "name": self.name,
            "type": self.rule_type,
            "when": [dict(condition.criteria) for condition in self.when],
            "then": [
                {
                    "belief_type": action.belief_type,
                    "predicate": action.predicate,
                    "object": action.object_literal,
                    **dict(action.metadata),
                }
                for action in self.then
            ],
            "confidence_delta": str(self.confidence_delta),
            "exceptions": [dict(condition.criteria) for condition in self.exceptions],
            "assumption_policy": self.assumption_policy,
            "is_active": self.is_active,
        }


def load_rule_definitions(paths: list[str | Path]) -> list[RuleDefinition]:
    """Load rule definitions from YAML files or directories."""
    definitions: list[RuleDefinition] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            definitions.extend(load_rule_definitions(sorted(path.glob("*.yaml"))))
            continue
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, list):
            mappings = loaded
        elif isinstance(loaded, dict) and "rules" in loaded:
            mappings = loaded["rules"]
        else:
            mappings = [loaded]
        for mapping in mappings:
            if not isinstance(mapping, Mapping):
                raise RuleDefinitionError(f"rule file {path} must contain mapping rules")
            definitions.append(RuleDefinition.from_mapping(mapping))
    return definitions


def field_value(support: object, key: str) -> Any:
    """Read a normalized field from an event, claim, belief, or mapping."""
    normalized_key = "object_literal" if key == "object" else key
    if isinstance(support, Mapping):
        if normalized_key in support:
            return support[normalized_key]
        if key in support:
            return support[key]
        if key == "subject":
            return support.get("subject_entity") or support.get("actor_entity")
        if key == "actor":
            return support.get("actor_entity") or support.get("subject_entity")
        return None

    if normalized_key == "object_literal":
        value = getattr(support, "object_literal", "")
        if value:
            return value
        entity = getattr(support, "object_entity", None)
        return _entity_name(entity)
    if key == "subject":
        return _entity_name(getattr(support, "subject_entity", None) or getattr(support, "actor_entity", None))
    if key == "actor":
        return _entity_name(getattr(support, "actor_entity", None) or getattr(support, "subject_entity", None))
    if key == "source":
        return _entity_name(getattr(support, "source", None)) or getattr(support, "source_id", None)
    value = getattr(support, normalized_key, None)
    return _entity_name(value) if hasattr(value, "canonical_name") or hasattr(value, "name") else value


def value_matches(actual: Any, expected: Any, *, key: str = "") -> bool:
    """Return whether an actual field value satisfies an expected rule value."""
    if isinstance(expected, (list, tuple, set)):
        return any(value_matches(actual, item, key=key) for item in expected)
    actual_value = _normalize_value(actual)
    expected_value = _normalize_value(expected)
    if not expected_value:
        return not actual_value
    if key in _EXACT_MATCH_FIELDS:
        return actual_value == expected_value
    if key in _OBJECT_FIELDS:
        return actual_value == expected_value or expected_value in actual_value.split("_") or expected_value in actual_value
    return actual_value == expected_value


def _parse_conditions(value: Any, *, field_name: str, required: bool = True) -> tuple[RuleCondition, ...]:
    if value is None:
        if required:
            raise RuleDefinitionError(f"{field_name} conditions are required")
        return ()
    entries = value if isinstance(value, list) else [value]
    conditions: list[RuleCondition] = []
    for entry in entries:
        if not isinstance(entry, Mapping) or not entry:
            raise RuleDefinitionError(f"{field_name} entries must be non-empty mappings")
        conditions.append(RuleCondition(dict(entry)))
    if required and not conditions:
        raise RuleDefinitionError(f"{field_name} conditions are required")
    return tuple(conditions)


def _parse_actions(value: Any) -> tuple[RuleAction, ...]:
    if value is None:
        raise RuleDefinitionError("then actions are required")
    entries = value if isinstance(value, list) else [value]
    actions: list[RuleAction] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise RuleDefinitionError("then entries must be mappings")
        belief_type = str(entry.get("belief_type") or "").strip()
        predicate = str(entry.get("predicate") or "").strip()
        object_literal = str(entry.get("object") or entry.get("object_literal") or "").strip()
        if not belief_type or not predicate:
            raise RuleDefinitionError("then actions require belief_type and predicate")
        metadata = {key: value for key, value in entry.items() if key not in {"belief_type", "predicate", "object", "object_literal"}}
        actions.append(RuleAction(belief_type=belief_type, predicate=predicate, object_literal=object_literal, metadata=metadata))
    if not actions:
        raise RuleDefinitionError("then actions are required")
    return tuple(actions)


def _parse_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuleDefinitionError(f"{field_name} must be numeric") from exc


def _entity_name(value: object | None) -> str:
    if value is None:
        return ""
    return str(getattr(value, "canonical_name", "") or getattr(value, "name", "") or value)


def _normalize_value(value: Any) -> str:
    if value is None:
        return ""
    return "_".join(str(value).strip().lower().replace("-", "_").split())
