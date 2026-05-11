"""Digest payload and daily digest generation."""

from datetime import date, datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from monitoring.models import (
    AlertHit,
    DailyDigest,
    DigestCache,
    NormalizedDocument,
    Source,
    TopicCluster,
)

DIGEST_CACHE_KEY = "feed-digest:v1"
DIGEST_TTL_MINUTES = 15
MAX_ITEMS_PER_CATEGORY = 20
MAX_ITEMS_PER_SOURCE = 5


def list_feed_digest_payload() -> dict[str, object]:
    """Return cached categorized feed digest payload.

    Example:
        `payload = list_feed_digest_payload()`
    """
    cached = _fresh_cache()
    if cached is not None:
        return cached
    payload = _build_feed_digest_payload()
    _store_cache(payload)
    return payload


def build_daily_digest(digest_date: date) -> DailyDigest:
    """Create or update a plain-text daily digest.

    Example:
        `digest = build_daily_digest(date.today())`
    """
    payload = _build_feed_digest_payload()
    body = _daily_digest_body(digest_date, payload)
    digest, _created = DailyDigest.objects.update_or_create(
        digest_date=digest_date,
        defaults=_daily_digest_defaults(digest_date, body, payload),
    )
    return digest


def _fresh_cache() -> dict[str, object] | None:
    cache = DigestCache.objects.filter(
        cache_key=DIGEST_CACHE_KEY,
        expires_at__gt=timezone.now(),
    ).first()
    if cache is None:
        return None
    return dict(cache.payload)


def _store_cache(payload: dict[str, object]) -> None:
    DigestCache.objects.update_or_create(
        cache_key=DIGEST_CACHE_KEY,
        defaults={
            "payload": payload,
            "created_at": timezone.now(),
            "expires_at": timezone.now() + timedelta(minutes=DIGEST_TTL_MINUTES),
        },
    )


def _build_feed_digest_payload() -> dict[str, object]:
    documents = NormalizedDocument.objects.select_related("source").order_by(
        "-source__reputation_score",
        "-published_at",
        "-created_at",
    )
    grouped = _group_documents_by_category(documents)
    return {
        "generated_at": timezone.now().isoformat(),
        "categories": grouped,
        "top_clusters": _top_clusters(),
        "alert_counts": _alert_counts(),
    }


def _group_documents_by_category(
    documents: QuerySet[NormalizedDocument],
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    source_counts: dict[tuple[str, int], int] = {}
    for document in documents:
        category = document.source.category
        if _category_is_full(grouped, category):
            continue
        if _source_is_full(source_counts, category, document.source_id):
            continue
        grouped.setdefault(category, []).append(_document_digest_item(document))
        source_key = (category, document.source_id)
        source_counts[source_key] = source_counts.get(source_key, 0) + 1
    return grouped


def _category_is_full(
    grouped: dict[str, list[dict[str, object]]], category: str
) -> bool:
    return len(grouped.get(category, [])) >= MAX_ITEMS_PER_CATEGORY


def _source_is_full(
    source_counts: dict[tuple[str, int], int],
    category: str,
    source_id: int,
) -> bool:
    return source_counts.get((category, source_id), 0) >= MAX_ITEMS_PER_SOURCE


def _document_digest_item(document: NormalizedDocument) -> dict[str, object]:
    return {
        "id": document.id,
        "title": document.title,
        "url": document.canonical_url,
        "source": document.source.name,
        "source_id": document.source_id,
        "published_at": _optional_isoformat(document.published_at),
        "entities": document.entities[:8],
        "tags": document.tags,
        "snippet": document.content[:400],
        "source_reputation": str(document.source.reputation_score),
    }


def _top_clusters() -> list[dict[str, object]]:
    clusters = TopicCluster.objects.all()[:5]
    return [
        {
            "label": cluster.label,
            "document_count": cluster.document_count,
            "score": str(cluster.score),
            "keywords": cluster.keywords[:8],
        }
        for cluster in clusters
    ]


def _alert_counts() -> dict[str, int]:
    return {
        "open": AlertHit.objects.filter(status=AlertHit.Status.OPEN).count(),
        "acknowledged": AlertHit.objects.filter(
            status=AlertHit.Status.ACKNOWLEDGED
        ).count(),
        "resolved": AlertHit.objects.filter(status=AlertHit.Status.RESOLVED).count(),
    }


def _daily_digest_body(digest_date: date, payload: dict[str, object]) -> str:
    lines = [f"Daily Digest for {digest_date.isoformat()}", ""]
    categories = payload.get("categories", {})
    if isinstance(categories, dict):
        _append_category_lines(lines, categories)
    return "\n".join(lines).strip()


def _append_category_lines(lines: list[str], categories: dict[object, object]) -> None:
    for category, raw_items in categories.items():
        if not isinstance(raw_items, list):
            continue
        lines.extend(["", str(category).title()])
        for item in raw_items[:10]:
            lines.append(_digest_line(item))


def _digest_line(item: object) -> str:
    if not isinstance(item, dict):
        return "- Invalid digest item"
    return f"- {item.get('title', 'Untitled')} ({item.get('source', 'Unknown')})"


def _daily_digest_defaults(
    digest_date: date,
    body: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "title": f"Daily Digest {digest_date.isoformat()}",
        "body": body,
        "metrics": _digest_metrics(payload),
    }


def _digest_metrics(payload: dict[str, object]) -> dict[str, object]:
    categories = payload.get("categories", {})
    if not isinstance(categories, dict):
        return {"category_count": 0, "item_count": 0}
    item_count = sum(
        len(value) for value in categories.values() if isinstance(value, list)
    )
    return {"category_count": len(categories), "item_count": item_count}


def _optional_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
