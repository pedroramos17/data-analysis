"""Phase 12 extraction evaluation harness.

Runs the real entity/claim/event extractors over the gold documents and scores
them against the gold labels, producing the metrics named in the Phase 12 spec:
entity/claim/event precision and recall, evidence-span accuracy, and
contradiction-detection accuracy.

Design notes that keep the numbers honest:

* Matching is lenient on phrasing but strict on identity. Claims match on
  (subject, predicate); events on (actor, event_type); entities on canonical
  name. This rewards correct structure without punishing trivial wording.
* The gold set deliberately includes items the heuristic extractor cannot reach
  (verbs outside its pattern) and pattern sentences left unlabeled, so recall
  and precision land below 1.0 -- the eval discriminates instead of rubber-
  stamping.
* Contradiction detection is scored on its own pass: the gold contradiction
  claims are persisted with their labeled polarity and run through
  ``detect_claim_contradictions``; we measure how many labeled pairs are found.

The harness mutates the database, so call it inside a test transaction (or a
throwaway DB). Entry point: :func:`evaluate_extraction`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path

DEFAULT_GOLD_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


@dataclass
class PrecisionRecall:
    true_positives: int = 0
    predicted: int = 0
    gold: int = 0

    @property
    def precision(self) -> float:
        return self.true_positives / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.gold if self.gold else 0.0

    def to_dict(self) -> dict[str, float]:
        return {"precision": round(self.precision, 4), "recall": round(self.recall, 4),
                "tp": self.true_positives, "predicted": self.predicted, "gold": self.gold}


@dataclass
class ExtractionMetrics:
    entities: PrecisionRecall = field(default_factory=PrecisionRecall)
    claims: PrecisionRecall = field(default_factory=PrecisionRecall)
    events: PrecisionRecall = field(default_factory=PrecisionRecall)
    evidence_spans_correct: int = 0
    evidence_spans_total: int = 0
    contradiction_pairs_gold: int = 0
    contradiction_pairs_detected: int = 0

    @property
    def evidence_span_accuracy(self) -> float:
        return self.evidence_spans_correct / self.evidence_spans_total if self.evidence_spans_total else 0.0

    @property
    def contradiction_detection_accuracy(self) -> float:
        return self.contradiction_pairs_detected / self.contradiction_pairs_gold if self.contradiction_pairs_gold else 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "entity_precision": round(self.entities.precision, 4),
            "entity_recall": round(self.entities.recall, 4),
            "claim_precision": round(self.claims.precision, 4),
            "claim_recall": round(self.claims.recall, 4),
            "event_precision": round(self.events.precision, 4),
            "event_recall": round(self.events.recall, 4),
            "evidence_span_accuracy": round(self.evidence_span_accuracy, 4),
            "contradiction_detection_accuracy": round(self.contradiction_detection_accuracy, 4),
            "support": {
                "entities": self.entities.to_dict(),
                "claims": self.claims.to_dict(),
                "events": self.events.to_dict(),
                "evidence_spans": {"correct": self.evidence_spans_correct, "total": self.evidence_spans_total},
                "contradictions": {"gold": self.contradiction_pairs_gold, "detected": self.contradiction_pairs_detected},
            },
        }


def load_gold(gold_dir: Path | str | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    base = Path(gold_dir) if gold_dir else DEFAULT_GOLD_DIR
    documents = _read_jsonl(base / "gold_documents.jsonl")
    claims = _read_jsonl(base / "gold_claims.jsonl")
    events = _read_jsonl(base / "gold_events.jsonl")
    return documents, claims, events


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def evaluate_extraction(gold_dir: Path | str | None = None) -> ExtractionMetrics:
    """Run extractors over the gold corpus and compute Phase 12 metrics."""
    from django.utils import timezone
    from sourceflow import models
    from sourceflow.claims import extract_and_persist_document_claims
    from sourceflow.events import extract_and_persist_document_events
    from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document

    documents, gold_claims, gold_events = load_gold(gold_dir)
    gold_claims_by_doc: dict[str, list[dict]] = {}
    gold_events_by_doc: dict[str, list[dict]] = {}
    for claim in gold_claims:
        gold_claims_by_doc.setdefault(claim["doc_id"], []).append(claim)
    for event in gold_events:
        gold_events_by_doc.setdefault(event["doc_id"], []).append(event)

    metrics = ExtractionMetrics()

    for gold_doc in documents:
        source = _source_for(gold_doc)
        published = _parse_dt(gold_doc.get("published_at")) or timezone.now()
        document = persist_normalized_document(
            DocumentInput(
                source_id=source.pk,
                url=gold_doc["url"],
                title=gold_doc.get("title", ""),
                raw_text=gold_doc["text"],
                published_at=published,
            ),
            max_chunk_chars=200,
            chunk_overlap=0,
        ).document

        predicted_claims = [r.claim for r in extract_and_persist_document_claims(document) if r.claim is not None]
        predicted_events = [r.event for r in extract_and_persist_document_events(document)]

        # ----- entities -----
        gold_entities = {_norm(entity["name"]) for entity in gold_doc.get("entities", [])}
        predicted_entities = set()
        for claim in predicted_claims:
            predicted_entities.add(_norm(claim.subject_entity.canonical_name))
            if claim.object_entity_id:
                predicted_entities.add(_norm(claim.object_entity.canonical_name))
        for event in predicted_events:
            predicted_entities.add(_norm(event.actor_entity.canonical_name))
        _accumulate(metrics.entities, predicted_entities, gold_entities)

        # ----- claims (subject, predicate) -----
        gold_claim_keys = {(_norm(c["subject"]), _norm(c["predicate"])) for c in gold_claims_by_doc.get(gold_doc["doc_id"], [])}
        predicted_claim_index = {
            (_norm(c.subject_entity.canonical_name), _norm(c.predicate)): c for c in predicted_claims
        }
        _accumulate(metrics.claims, set(predicted_claim_index), gold_claim_keys)

        # ----- evidence-span accuracy (over matched claims) -----
        for gold_claim in gold_claims_by_doc.get(gold_doc["doc_id"], []):
            key = (_norm(gold_claim["subject"]), _norm(gold_claim["predicate"]))
            predicted = predicted_claim_index.get(key)
            if predicted is None:
                continue
            metrics.evidence_spans_total += 1
            span_text = _norm(getattr(predicted.evidence_span, "text", ""))
            gold_evidence = _norm(gold_claim["evidence_text"])
            if gold_evidence and (gold_evidence in span_text or span_text in gold_evidence):
                metrics.evidence_spans_correct += 1

        # ----- events (actor, event_type) -----
        gold_event_keys = {(_norm(e["actor"]), _norm(e["event_type"])) for e in gold_events_by_doc.get(gold_doc["doc_id"], [])}
        predicted_event_keys = {(_norm(e.actor_entity.canonical_name), _norm(e.event_type)) for e in predicted_events}
        _accumulate(metrics.events, predicted_event_keys, gold_event_keys)

    _score_contradictions(metrics, gold_claims)
    return metrics


def _accumulate(bucket: PrecisionRecall, predicted: set, gold: set) -> None:
    bucket.true_positives += len(predicted & gold)
    bucket.predicted += len(predicted)
    bucket.gold += len(gold)


def _score_contradictions(metrics: ExtractionMetrics, gold_claims: list[dict]) -> None:
    """Persist labeled contradiction claims and measure detector recall."""
    from sourceflow.claims import ClaimCandidate, persist_claim_candidates
    from sourceflow.entities import create_or_update_entity
    from sourceflow.ingestion.normalizer import DocumentInput, persist_normalized_document
    from sourceflow.models import Source
    from sourceflow.reasoning.contradictions import claim_key, detect_claim_contradictions

    # Gold contradiction pairs: same (subject, predicate, object), opposite polarity.
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for claim in gold_claims:
        grouped.setdefault((_norm(claim["subject"]), _norm(claim["predicate"]), _norm(claim["object"])), []).append(claim)
    gold_pairs = [
        (left, right)
        for group in grouped.values()
        for i, left in enumerate(group)
        for right in group[i + 1 :]
        if _norm(left["polarity"]) != _norm(right["polarity"])
    ]
    metrics.contradiction_pairs_gold = len(gold_pairs)
    if not gold_pairs:
        return

    source, _ = Source.objects.get_or_create(
        name="Contradiction Eval Source",
        defaults={"url": "https://example.test/contradiction-eval", "source_type": Source.SourceType.OTHER},
    )
    # Persist every gold claim that participates in a contradiction, with its label.
    involved = {id(c) for pair in gold_pairs for c in pair}
    persisted: dict[str, object] = {}
    for claim in gold_claims:
        if id(claim) not in involved:
            continue
        create_or_update_entity(canonical_name=claim["subject"], entity_type="Company")
        document = persist_normalized_document(
            DocumentInput(source_id=source.pk, url=f"https://example.test/ce-{claim['claim_id']}",
                          title="contradiction eval", raw_text=claim["evidence_text"]),
            max_chunk_chars=200, chunk_overlap=0,
        ).document
        result = persist_claim_candidates(
            document,
            [ClaimCandidate(
                subject_text=claim["subject"], predicate=claim["predicate"],
                object_text=claim["object"], object_literal=claim["object"],
                polarity=_norm(claim["polarity"]), confidence=Decimal("0.80"),
                evidence_text=claim["evidence_text"],
            )],
        )
        persisted[claim["claim_id"]] = result[0].claim

    detected = detect_claim_contradictions(list(persisted.values()))
    detected_keys = set()
    for result in detected:
        detected_keys.add(frozenset({claim_key(result.left_claim), claim_key(result.right_claim)}))

    for left, right in gold_pairs:
        left_claim, right_claim = persisted.get(left["claim_id"]), persisted.get(right["claim_id"])
        if left_claim is None or right_claim is None:
            continue
        pair_key = frozenset({claim_key(left_claim), claim_key(right_claim)})
        if pair_key in detected_keys:
            metrics.contradiction_pairs_detected += 1


def _source_for(gold_doc: dict) -> object:
    from sourceflow.models import ProviderOwner, Source

    owner = None
    owner_name = gold_doc.get("owner")
    if owner_name:
        owner, _ = ProviderOwner.objects.get_or_create(name=owner_name, defaults={"canonical_name": owner_name})
    source, _ = Source.objects.get_or_create(
        name=gold_doc["source"],
        defaults={
            "url": f"https://example.test/source/{_norm(gold_doc['source']).replace(' ', '-')}",
            "source_type": Source.SourceType.RSS,
            "language": gold_doc.get("language", "en"),
            "reliability_score": Decimal(str(gold_doc.get("reliability_score", 0))),
            "bias_tags": gold_doc.get("bias_tags", []),
            "provider_owner": owner,
        },
    )
    return source


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
