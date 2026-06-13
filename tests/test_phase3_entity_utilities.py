"""Phase 3 dependency-light entity utility tests."""

from __future__ import annotations

import unittest

from sourceflow.entities import (
    HeuristicEntityExtractor,
    normalize_alias,
    normalize_identifier,
)


class Phase3EntityUtilityTests(unittest.TestCase):
    def test_normalize_alias_handles_company_punctuation(self) -> None:
        self.assertEqual(normalize_alias("Meta Platforms, Inc."), "meta platforms inc")

    def test_normalize_identifier_removes_punctuation_and_uppercases(self) -> None:
        self.assertEqual(normalize_identifier("us-30303m1027"), "US30303M1027")

    def test_heuristic_extractor_returns_spans_types_and_confidence(self) -> None:
        text = "Meta Platforms and Facebook discussed META on NASDAQ:META."
        candidates = HeuristicEntityExtractor().extract(text)
        by_text = {candidate.text: candidate for candidate in candidates}

        self.assertIn("Meta Platforms", by_text)
        self.assertIn("Facebook", by_text)
        self.assertIn("META", by_text)
        self.assertEqual(by_text["META"].entity_type, "Security")
        self.assertEqual(text[by_text["META"].char_start : by_text["META"].char_end], "META")
        self.assertGreater(by_text["META"].confidence, 0)


if __name__ == "__main__":
    unittest.main()
