"""Build retrieval-ready GraphRAG event context documents."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from django.db.models import QuerySet

from monitoring.models import DocumentTopic, TopicCluster
from sourceflow.intelligence.xai.explain_factor import explain_factor
from sourceflow.intelligence.xai.graph_trace import graph_trace_for_event


@dataclass(frozen=True, slots=True)
class GraphRagEventContext:
    """Retrieval-ready context for one event cluster.

    Example:
        `context = build_event_rag_context(1, Path("data"))`
    """

    event_id: int
    event_title: str
    time_range: dict[str, str]
    top_articles: tuple[dict[str, object], ...]
    top_sources: tuple[str, ...]
    top_providers: tuple[str, ...]
    top_entities: tuple[str, ...]
    top_claims: tuple[str, ...]
    evidence_spans: tuple[str, ...]
    dominant_frames: tuple[str, ...]
    graph_neighborhood: tuple[dict[str, object], ...]
    top_factor_scores: tuple[dict[str, object], ...]
    source_comparison: tuple[dict[str, object], ...]
    provider_comparison: tuple[dict[str, object], ...]


def build_event_rag_context(event_id: int, output_dir: Path) -> GraphRagEventContext:
    """Build JSON and Markdown GraphRAG context for one event.

    Example:
        `build_event_rag_context(42, Path("data"))`
    """
    cluster = TopicCluster.objects.get(id=event_id)
    topics = _cluster_topics(cluster)
    context = _context_from_topics(cluster, topics)
    _write_context(context, output_dir)
    return context


def _context_from_topics(
    cluster: TopicCluster,
    topics: QuerySet[DocumentTopic],
) -> GraphRagEventContext:
    documents = [topic.document for topic in topics]
    return GraphRagEventContext(
        event_id=cluster.id,
        event_title=cluster.canonical_title or cluster.label,
        time_range=_time_range(cluster),
        top_articles=tuple(_article_row(document) for document in documents[:10]),
        top_sources=tuple(
            dict.fromkeys(document.source.name for document in documents)
        ),
        top_providers=tuple(
            dict.fromkeys(_provider(document) for document in documents)
        ),
        top_entities=_top_entities(documents),
        top_claims=_top_claims(documents),
        evidence_spans=_evidence_spans(documents),
        dominant_frames=_dominant_frames(documents),
        graph_neighborhood=tuple(graph_trace_for_event(cluster.id)),
        top_factor_scores=_factor_summaries(),
        source_comparison=_source_comparison(documents),
        provider_comparison=_provider_comparison(documents),
    )


def _cluster_topics(cluster: TopicCluster) -> QuerySet[DocumentTopic]:
    return (
        DocumentTopic.objects.filter(cluster=cluster)
        .select_related("document", "document__source")
        .order_by("-overlap_score", "-similarity")
    )


def _time_range(cluster: TopicCluster) -> dict[str, str]:
    return {
        "start": cluster.window_start.isoformat(),
        "end": cluster.window_end.isoformat(),
    }


def _article_row(document: object) -> dict[str, object]:
    return {
        "id": document.id,
        "title": document.title,
        "source": document.source.name,
        "provider": _provider(document),
        "published_at": document.published_at.isoformat(),
    }


def _provider(document: object) -> str:
    metadata = document.metadata or {}
    return str(
        metadata.get("provider")
        or document.source.query_template
        or document.source.name
    )


def _top_entities(documents: list[object]) -> tuple[str, ...]:
    values: list[str] = []
    for document in documents:
        values.extend(str(entity) for entity in document.entities or ())
    return tuple(dict.fromkeys(values))


def _top_claims(documents: list[object]) -> tuple[str, ...]:
    return tuple(document.title for document in documents[:10])


def _evidence_spans(documents: list[object]) -> tuple[str, ...]:
    return tuple(
        (document.text or document.content or "")[:160] for document in documents[:10]
    )


def _dominant_frames(documents: list[object]) -> tuple[str, ...]:
    frames: list[str] = []
    for document in documents:
        frames.extend(
            str(frame) for frame in (document.metadata or {}).get("frames", ())
        )
    return tuple(dict.fromkeys(frames))


def _factor_summaries() -> tuple[dict[str, object], ...]:
    names = ("coverage_intensity", "provider_amplification", "event_conflict_risk")
    return tuple({"name": name, "explanation": explain_factor(name)} for name in names)


def _source_comparison(documents: list[object]) -> tuple[dict[str, object], ...]:
    counts = _counts(document.source.name for document in documents)
    return tuple(
        {"source": key, "article_count": value} for key, value in counts.items()
    )


def _provider_comparison(documents: list[object]) -> tuple[dict[str, object], ...]:
    counts = _counts(_provider(document) for document in documents)
    return tuple(
        {"provider": key, "article_count": value} for key, value in counts.items()
    )


def _counts(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _write_context(context: GraphRagEventContext, output_dir: Path) -> None:
    directory = output_dir / "graphrag_context" / "events"
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{context.event_id}.json"
    md_path = directory / f"{context.event_id}.md"
    json_path.write_text(json.dumps(asdict(context), indent=2), encoding="utf-8")
    md_path.write_text(_markdown(context), encoding="utf-8")


def _markdown(context: GraphRagEventContext) -> str:
    articles = "\n".join(
        f"- {row['title']} ({row['source']})" for row in context.top_articles
    )
    return (
        f"# {context.event_title}\n\n"
        "Neutral Sourceflow comparison context. This document describes coverage "
        "asymmetry, provider concentration, framing divergence, evidence density, "
        "claim disagreement, possible omission, and amplification patterns.\n\n"
        f"## Articles\n{articles}\n"
    )
