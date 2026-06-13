"""The sourceflow document pipeline stages.

Each stage is a small function over a :class:`PipelineContext` that delegates to
the real sourceflow operation for that step and returns a :class:`StageResult`
carrying output counts plus the model/extractor versions it used (so the runner
can log document id + model versions per the Phase 13 acceptance criteria).

Stages are independently runnable: per-document stages load the document from the
job and recompute any in-memory artifact they need from the database, so running
just ``extract_claims`` on an existing document works without first re-running
ingest/normalize/chunk in the same process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class PipelineStageError(RuntimeError):
    """Raised when a stage cannot run (e.g. missing prerequisite state)."""


@dataclass
class StageResult:
    output: dict[str, Any]
    model_versions: dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineContext:
    job: Any
    payload: dict[str, Any] = field(default_factory=dict)
    document_id: int | None = None
    scratch: dict[str, Any] = field(default_factory=dict)

    def document(self) -> Any:
        from sourceflow.models import Document

        if self.document_id is None:
            raise PipelineStageError("no document in context; run 'ingest' first or attach a document to the job")
        try:
            return Document.objects.get(pk=self.document_id)
        except Document.DoesNotExist as exc:
            raise PipelineStageError(f"document {self.document_id} no longer exists") from exc


def _rules_dir() -> Path:
    from django.conf import settings

    base = getattr(settings, "BASE_DIR", None)
    if base and (Path(base) / "rules").exists():
        return Path(base) / "rules"
    return Path(__file__).resolve().parents[2] / "rules"


def _document_input(payload: dict[str, Any]) -> Any:
    from sourceflow.ingestion import DocumentInput

    return DocumentInput(
        source_id=payload["source_id"],
        url=payload.get("url", ""),
        title=payload.get("title", ""),
        raw_text=payload.get("raw_text", ""),
        published_at=payload.get("published_at"),
        language=payload.get("language", "en"),
    )


def _document_input_from_document(document: Any) -> Any:
    from sourceflow.ingestion import DocumentInput

    return DocumentInput(
        source_id=document.source_id,
        url=document.url,
        title=document.title,
        raw_text=document.raw_text,
        published_at=document.published_at,
        language=document.language,
    )


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #

def stage_ingest(ctx: PipelineContext) -> StageResult:
    from sourceflow.ingestion import normalize_document_input
    from sourceflow.models import Document, Source

    payload = ctx.payload
    if not payload.get("source_id"):
        raise PipelineStageError("ingest requires payload['source_id']")
    if not Source.objects.filter(pk=payload["source_id"]).exists():
        raise PipelineStageError(f"source {payload['source_id']} not found")
    normalized = normalize_document_input(_document_input(payload))
    ctx.scratch["normalized"] = normalized
    document = Document.objects.create(
        source_id=int(normalized.source_id),
        url=normalized.url,
        title=normalized.title,
        published_at=normalized.published_at,
        raw_text=normalized.raw_text,
        clean_text="",
        content_hash=normalized.content_hash,
        language=normalized.language,
        metadata_json=normalized.metadata_json,
        provenance_json=normalized.provenance_json,
    )
    ctx.document_id = document.pk
    ctx.job.document_id = document.pk
    ctx.job.save(update_fields=["document", "updated_at"])
    return StageResult(
        {"document_id": document.pk, "raw_chars": len(normalized.raw_text)},
        {"ingestion_version": normalized.ingestion_version},
    )


def stage_normalize(ctx: PipelineContext) -> StageResult:
    from sourceflow.ingestion import normalize_document_input

    document = ctx.document()
    normalized = ctx.scratch.get("normalized") or normalize_document_input(_document_input_from_document(document))
    ctx.scratch["normalized"] = normalized
    document.clean_text = normalized.clean_text
    document.content_hash = normalized.content_hash
    document.language = normalized.language
    document.save(update_fields=["clean_text", "content_hash", "language", "updated_at"])
    return StageResult(
        {"document_id": document.pk, "clean_chars": len(normalized.clean_text)},
        {"ingestion_version": normalized.ingestion_version},
    )


def stage_chunk(ctx: PipelineContext) -> StageResult:
    from sourceflow.ingestion import chunk_text
    from sourceflow.models import DocumentChunk

    document = ctx.document()
    normalized = ctx.scratch.get("normalized")
    chunks = normalized.chunks if normalized else chunk_text(document.clean_text or document.raw_text)
    version = getattr(normalized, "ingestion_version", "")
    count = 0
    for chunk in chunks:
        DocumentChunk.objects.update_or_create(
            document=document,
            chunk_index=chunk.chunk_index,
            defaults={
                "text": chunk.text,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_count": chunk.token_count,
                "content_hash": chunk.content_hash,
                "language": document.language,
                "ingestion_version": version,
            },
        )
        count += 1
    return StageResult({"document_id": document.pk, "chunks": count}, {"chunker": "sliding_window/1"})


def stage_extract_entities(ctx: PipelineContext) -> StageResult:
    from sourceflow.entities import HeuristicEntityExtractor, extract_candidates

    document = ctx.document()
    candidates = extract_candidates(document.clean_text or document.raw_text)
    ctx.scratch["entity_candidates"] = candidates
    version = getattr(HeuristicEntityExtractor, "name", "heuristic_entity_extractor")
    return StageResult(
        {"document_id": document.pk, "candidates": len(candidates)},
        {"entity_extractor": f"{version}/{getattr(HeuristicEntityExtractor, 'version', '1')}"},
    )


def stage_link_entities(ctx: PipelineContext) -> StageResult:
    from sourceflow.entities import extract_link_and_persist_document_mentions

    document = ctx.document()
    mentions = extract_link_and_persist_document_mentions(document)
    return StageResult(
        {"document_id": document.pk, "mentions": len(mentions)},
        {"entity_linker": "heuristic_entity_linker/1"},
    )


def stage_extract_claims(ctx: PipelineContext) -> StageResult:
    from sourceflow.claims import extract_and_persist_document_claims

    document = ctx.document()
    results = extract_and_persist_document_claims(document)
    persisted = [r for r in results if r.claim is not None]
    return StageResult(
        {"document_id": document.pk, "claims": len(persisted), "candidates": len(results)},
        {"claim_extractor": "heuristic_claim_extractor/1"},
    )


def stage_extract_events(ctx: PipelineContext) -> StageResult:
    from sourceflow.events import extract_and_persist_document_events

    document = ctx.document()
    results = extract_and_persist_document_events(document)
    return StageResult(
        {"document_id": document.pk, "events": len(results)},
        {"event_extractor": "heuristic_event_extractor/1"},
    )


def stage_update_kg(ctx: PipelineContext) -> StageResult:
    from sourceflow.kg import default_graph_store
    from sourceflow.models import Claim, Event

    document = ctx.document()
    store = default_graph_store()
    edges = 0
    for claim in Claim.objects.filter(document=document):
        edges += len(store.upsert_claim(claim))
    for event in Event.objects.filter(document=document):
        edges += len(store.upsert_event(event))
    return StageResult({"document_id": document.pk, "edges": edges}, {"graph_store": "SqlGraphStore/1"})


def stage_run_reasoning(ctx: PipelineContext) -> StageResult:
    from sourceflow.models import Event
    from sourceflow.reasoning import InferenceEngine

    document = ctx.document()
    events = list(Event.objects.filter(document=document))
    engine = InferenceEngine.from_default_rules(_rules_dir())
    engine.upsert_rules()
    results = engine.infer_from_events(events)
    created = [r for r in results if r.status == "created"]
    return StageResult(
        {"document_id": document.pk, "rule_results": len(results), "beliefs_created": len(created)},
        {"inference_rules": _rules_dir().name},
    )


def stage_update_tms(ctx: PipelineContext) -> StageResult:
    from sourceflow.tms import recompute_stale_beliefs

    recomputed = recompute_stale_beliefs()
    return StageResult(
        {"document_id": ctx.document_id, "recomputed_beliefs": len(recomputed)},
        {"tms": "1"},
    )


def stage_update_retrieval_index(ctx: PipelineContext) -> StageResult:
    from sourceflow.models import DocumentChunk

    document = ctx.document()
    chunks = list(DocumentChunk.objects.filter(document=document))
    # Hybrid retrieval (BM25 + vector) is built at query time over canonical
    # chunks, so this stage validates the corpus is indexable and reports size.
    token_total = sum(len((chunk.text or "").split()) for chunk in chunks)
    return StageResult(
        {"document_id": document.pk, "indexable_chunks": len(chunks), "tokens": token_total},
        {"retriever": "bm25+vector/1"},
    )


def stage_run_quant_signals(ctx: PipelineContext) -> StageResult:
    from sourceflow.models import Event
    from sourceflow.quant import RiskGraph, generate_event_alpha_candidates

    document = ctx.document()
    events = list(Event.objects.filter(document=document))
    risk_graph = RiskGraph()
    signals: list[Any] = []
    for event in events:
        signals.extend(risk_graph.propagate_event_risk(event))
    candidates = generate_event_alpha_candidates(events, sector_reactions={})
    return StageResult(
        {"document_id": document.pk, "risk_signals": len(signals), "alpha_candidates": len(candidates)},
        {"risk_rules": "risk_rules.yaml/1"},
    )


def stage_generate_reports(ctx: PipelineContext) -> StageResult:
    from sourceflow.models import Belief, Claim, DocumentChunk, Event, KnowledgeEdge

    document = ctx.document()
    report = {
        "document_id": document.pk,
        "title": document.title,
        "chunks": DocumentChunk.objects.filter(document=document).count(),
        "claims": Claim.objects.filter(document=document).count(),
        "events": Event.objects.filter(document=document).count(),
        "edges": KnowledgeEdge.objects.filter(source_document=document).count(),
        "beliefs": Belief.objects.filter(justifications__supporting_claim__document=document).distinct().count(),
    }
    ctx.job.report_json = report
    ctx.job.save(update_fields=["report_json", "updated_at"])
    return StageResult(report, {"reporter": "1"})


# Ordered pipeline definition.
STAGE_ORDER: list[str] = [
    "ingest",
    "normalize",
    "chunk",
    "extract_entities",
    "link_entities",
    "extract_claims",
    "extract_events",
    "update_kg",
    "run_reasoning",
    "update_tms",
    "update_retrieval_index",
    "run_quant_signals",
    "generate_reports",
]

STAGES: dict[str, Callable[[PipelineContext], StageResult]] = {
    "ingest": stage_ingest,
    "normalize": stage_normalize,
    "chunk": stage_chunk,
    "extract_entities": stage_extract_entities,
    "link_entities": stage_link_entities,
    "extract_claims": stage_extract_claims,
    "extract_events": stage_extract_events,
    "update_kg": stage_update_kg,
    "run_reasoning": stage_run_reasoning,
    "update_tms": stage_update_tms,
    "update_retrieval_index": stage_update_retrieval_index,
    "run_quant_signals": stage_run_quant_signals,
    "generate_reports": stage_generate_reports,
}
