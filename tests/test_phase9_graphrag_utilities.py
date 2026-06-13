"""Phase 9 dependency-light GraphRAG retrieval tests."""

from __future__ import annotations

import unittest
from decimal import Decimal

from sourceflow.graphrag import ConfidenceBreakdown, EvidenceItem, EvidencePack, EvidencePackError
from sourceflow.retrieval import BM25Index, TextDocument, VectorIndex, cosine_similarity, vectorize_text


class Phase9GraphRAGUtilityTests(unittest.TestCase):
    def test_bm25_retrieves_matching_text(self) -> None:
        index = BM25Index(
            [
                TextDocument("1", "Petrobras faces lawsuit risk", provenance={"document_id": "d1"}),
                TextDocument("2", "Vale reports production growth", provenance={"document_id": "d2"}),
            ]
        )

        hits = index.search("Petrobras lawsuit", limit=2)

        self.assertEqual(hits[0].identifier, "1")
        self.assertEqual(hits[0].retriever, "bm25")
        self.assertEqual(hits[0].provenance["document_id"], "d1")

    def test_vector_retrieval_uses_sparse_cosine_similarity(self) -> None:
        left = vectorize_text("lawsuit risk")
        right = vectorize_text("lawsuit litigation risk")
        index = VectorIndex([TextDocument("1", "lawsuit litigation risk")])

        self.assertGreater(cosine_similarity(left, right), 0)
        self.assertEqual(index.search("lawsuit risk")[0].identifier, "1")

    def test_evidence_pack_answer_requires_evidence_and_decomposes_confidence(self) -> None:
        empty_pack = EvidencePack(query="empty")
        with self.assertRaises(EvidencePackError):
            empty_pack.to_answer("No evidence answer")

        pack = EvidencePack(
            query="Petrobras lawsuit",
            supporting_claims=(
                EvidenceItem(
                    "supporting_claim",
                    "1",
                    "Petrobras faces lawsuit",
                    Decimal("0.80"),
                    {"source_id": 1, "document_id": 1, "evidence_span_id": 1},
                ),
            ),
            assumptions_used=("OWA", "PartialCWA"),
            confidence=ConfidenceBreakdown(Decimal("0.70"), Decimal("0.80"), Decimal("0.90")),
        )

        answer = pack.to_answer("Petrobras faces litigation risk.")

        self.assertEqual(answer["answer"], "Petrobras faces litigation risk.")
        self.assertEqual(answer["confidence"], 0.8)
        self.assertEqual(answer["confidence_breakdown"]["retrieval_confidence"], 0.7)
        self.assertEqual(answer["assumptions_used"], ["OWA", "PartialCWA"])
        self.assertTrue(answer["supporting_claims"])


if __name__ == "__main__":
    unittest.main()
