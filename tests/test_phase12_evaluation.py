"""Phase 12 Task 12.1 -- extraction evaluation harness over the gold dataset.

Runs the real extractors against the committed gold corpus and asserts the eight
named metrics are produced and land in sensible, *discriminating* bands: high
enough that extraction clearly works, but below 1.0 where the gold set contains
items the heuristic extractor cannot reach (so the eval actually measures
something rather than rubber-stamping).
"""

from __future__ import annotations

from django.test import TestCase

from sourceflow.evaluation import evaluate_extraction, load_gold


class Phase12ExtractionEvaluationTests(TestCase):
    def test_gold_corpus_is_present_and_consistent(self) -> None:
        documents, claims, events = load_gold()
        self.assertGreaterEqual(len(documents), 30)  # spec: 30-50 documents
        doc_ids = {d["doc_id"] for d in documents}
        # every labeled claim/event references a real document and a verbatim span
        text_by_doc = {d["doc_id"]: d["text"] for d in documents}
        for claim in claims:
            self.assertIn(claim["doc_id"], doc_ids)
            self.assertIn(claim["evidence_text"], text_by_doc[claim["doc_id"]])
        for event in events:
            self.assertIn(event["evidence_text"], text_by_doc[event["doc_id"]])

    def test_extraction_metrics_are_computed_and_discriminating(self) -> None:
        metrics = evaluate_extraction().to_dict()

        # All eight named metrics present and in [0, 1].
        for key in (
            "entity_precision", "entity_recall", "claim_precision", "claim_recall",
            "event_precision", "event_recall", "evidence_span_accuracy",
            "contradiction_detection_accuracy",
        ):
            self.assertIn(key, metrics)
            self.assertGreaterEqual(metrics[key], 0.0)
            self.assertLessEqual(metrics[key], 1.0)

        # Extraction clearly works: recall is high on the extractable majority.
        self.assertGreaterEqual(metrics["claim_recall"], 0.7)
        self.assertGreaterEqual(metrics["event_recall"], 0.6)
        self.assertGreaterEqual(metrics["entity_recall"], 0.8)

        # But the eval discriminates: gold items using non-pattern verbs are
        # missed, so claim recall is strictly below perfect.
        self.assertLess(metrics["claim_recall"], 1.0)
        # And unlabeled pattern sentences (traps) cost precision.
        self.assertLess(metrics["claim_precision"], 1.0)

        # Matched claims point at the right evidence span.
        self.assertGreaterEqual(metrics["evidence_span_accuracy"], 0.9)

        # Labeled contradictions are detected.
        self.assertGreaterEqual(metrics["support"]["contradictions"]["gold"], 3)
        self.assertGreaterEqual(metrics["contradiction_detection_accuracy"], 0.66)
