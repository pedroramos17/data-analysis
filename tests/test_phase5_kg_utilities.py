"""Phase 5 dependency-light knowledge graph schema tests."""

from __future__ import annotations

import unittest

from sourceflow.kg.schema import (
    ALLOWED_EDGES,
    NODE_TYPES,
    GraphSchemaError,
    is_allowed_edge,
    node_ref,
    validate_edge,
)


class Phase5GraphSchemaTests(unittest.TestCase):
    def test_node_ref_validates_type_and_id(self) -> None:
        ref = node_ref("entity", 42)

        self.assertEqual(ref.node_type, "entity")
        self.assertEqual(ref.node_id, "42")

    def test_node_ref_rejects_unknown_type_and_empty_id(self) -> None:
        with self.assertRaises(GraphSchemaError):
            node_ref("spaceship", 1)
        with self.assertRaises(GraphSchemaError):
            node_ref("entity", "")

    def test_every_allowed_edge_pair_uses_known_node_types(self) -> None:
        for edge_type, pairs in ALLOWED_EDGES.items():
            for source_type, target_type in pairs:
                self.assertIn(source_type, NODE_TYPES, edge_type)
                self.assertIn(target_type, NODE_TYPES, edge_type)

    def test_validate_edge_accepts_allowed_pair(self) -> None:
        validate_edge("about_subject", node_ref("claim", 1), node_ref("entity", 2))

    def test_validate_edge_rejects_unknown_edge_type(self) -> None:
        with self.assertRaises(GraphSchemaError):
            validate_edge("teleports_to", node_ref("claim", 1), node_ref("entity", 2))

    def test_validate_edge_rejects_disallowed_endpoint_pair(self) -> None:
        self.assertFalse(is_allowed_edge("about_subject", "entity", "claim"))
        with self.assertRaises(GraphSchemaError):
            validate_edge("about_subject", node_ref("entity", 2), node_ref("claim", 1))


if __name__ == "__main__":
    unittest.main()
