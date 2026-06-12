"""Phase 7 dependency-light rule parsing and matching tests."""

from __future__ import annotations

import unittest
from decimal import Decimal

from sourceflow.reasoning.rules import (
    RULE_TYPES,
    RuleDefinition,
    RuleDefinitionError,
    load_rule_definitions,
)


class Phase7RuleUtilityTests(unittest.TestCase):
    def test_rule_definition_parses_default_rule(self) -> None:
        definition = RuleDefinition.from_mapping(
            {
                "id": "legal_event_increases_risk",
                "type": "default",
                "when": [{"event_type": "lawsuit"}, {"polarity": "negative"}],
                "then": [
                    {
                        "belief_type": "risk",
                        "predicate": "increases",
                        "object": "litigation_risk",
                    }
                ],
                "confidence_delta": 0.2,
                "exceptions": [{"object": "immaterial_amount"}],
            }
        )

        self.assertEqual(definition.rule_type, "default")
        self.assertEqual(definition.confidence_delta, Decimal("0.2"))
        self.assertEqual(definition.then[0].object_literal, "litigation_risk")

    def test_rule_types_are_supported(self) -> None:
        self.assertEqual(
            RULE_TYPES,
            {
                "deductive",
                "default",
                "abductive",
                "diagnostic",
                "risk_propagation",
                "source_comparison",
                "retrieval_expansion",
            },
        )

    def test_rule_matching_and_exceptions(self) -> None:
        definition = RuleDefinition.from_mapping(
            {
                "id": "legal_event_increases_risk",
                "type": "default",
                "when": [{"event_type": "lawsuit"}, {"polarity": "negative"}],
                "then": [{"belief_type": "risk", "predicate": "increases", "object": "litigation_risk"}],
                "exceptions": [{"object": "immaterial_amount"}],
            }
        )

        self.assertTrue(
            definition.matches(
                {
                    "event_type": "lawsuit",
                    "polarity": "negative",
                    "object_literal": "a lawsuit",
                }
            )
        )
        self.assertTrue(
            definition.blocked_by_exception(
                {
                    "event_type": "lawsuit",
                    "polarity": "negative",
                    "object_literal": "an immaterial amount",
                }
            )
        )

    def test_load_default_rule_yaml(self) -> None:
        definitions = load_rule_definitions(["rules/legal_event_increases_risk.yaml"])

        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0].rule_id, "legal_event_increases_risk")
        self.assertEqual(definitions[0].rule_type, "default")

    def test_invalid_rule_rejected(self) -> None:
        with self.assertRaises(RuleDefinitionError):
            RuleDefinition.from_mapping({"id": "bad", "type": "teleport", "when": [], "then": []})


if __name__ == "__main__":
    unittest.main()
