"""Phase 2 dependency-light ingestion utility tests."""

from __future__ import annotations

import unittest

from sourceflow.ingestion import (
    DocumentInput,
    canonicalize_url,
    chunk_containing_span,
    chunk_text,
    detect_duplicate_hash,
    document_content_hash,
    extract_evidence_span,
    normalize_document_input,
)


class Phase2IngestionUtilityTests(unittest.TestCase):
    def test_canonicalize_url_strips_tracking_and_fragment(self) -> None:
        url = canonicalize_url("HTTPS://Example.test:443/a/?utm_source=x&b=2#frag")

        self.assertEqual(url, "https://example.test/a?b=2")

    def test_document_hash_is_whitespace_stable(self) -> None:
        left = document_content_hash("Petrobras\nfaces   investigation")
        right = document_content_hash("Petrobras faces investigation")

        self.assertEqual(left, right)

    def test_duplicate_hash_detection_marks_known_hash(self) -> None:
        candidate = document_content_hash("same document")
        result = detect_duplicate_hash({candidate}, candidate)

        self.assertTrue(result.is_duplicate)
        self.assertEqual(result.reason, "content_hash")

    def test_chunk_text_preserves_offsets(self) -> None:
        text = "Alpha beta gamma delta epsilon zeta eta theta iota kappa"
        chunks = chunk_text(text, max_chars=24, overlap=5)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(text[chunk.char_start : chunk.char_end], chunk.text)
            self.assertGreater(chunk.token_count, 0)

        containing = chunk_containing_span(chunks, text.index("gamma"), text.index("gamma") + len("gamma"))

        self.assertIsNotNone(containing)
        self.assertIn("gamma", containing.text)

    def test_normalize_document_input_builds_hash_chunks_and_metadata(self) -> None:
        normalized = normalize_document_input(
            DocumentInput(
                source_id=7,
                url="https://Example.test/post?utm_campaign=x&id=1",
                title=" Petrobras   News ",
                raw_text="Petrobras\nfaces   regulatory investigation.",
                published_at="2026-01-02T03:04:05Z",
                language="EN",
                external_id="article-1",
            ),
            ingestion_version="test.v1",
            max_chunk_chars=32,
            chunk_overlap=4,
        )

        self.assertEqual(normalized.url, "https://example.test/post?id=1")
        self.assertEqual(normalized.title, "Petrobras News")
        self.assertEqual(normalized.clean_text, "Petrobras faces regulatory investigation.")
        self.assertEqual(normalized.language, "en")
        self.assertEqual(normalized.metadata_json["ingestion_version"], "test.v1")
        self.assertEqual(normalized.metadata_json["external_id"], "article-1")
        self.assertTrue(normalized.content_hash)
        self.assertTrue(normalized.dedupe_key)
        self.assertGreaterEqual(len(normalized.chunks), 1)

    def test_extract_evidence_span_returns_offsets(self) -> None:
        span = extract_evidence_span(
            "Petrobras faces a regulatory investigation.",
            "regulatory investigation",
            extractor_name="unit-test",
            extractor_version="1",
            confidence="0.9",
        )

        self.assertEqual(span.char_start, 18)
        self.assertEqual(span.char_end, 42)
        self.assertEqual(span.extractor_name, "unit-test")


if __name__ == "__main__":
    unittest.main()
