"""Local source discovery from normalized public documents."""

import re
from decimal import Decimal
from urllib.parse import urlsplit

from django.utils import timezone

from monitoring.models import DiscoveryCandidate, NormalizedDocument, Source

RSS_HINT_PATTERN = re.compile(r"https?://[^\s\"'<>]+(?:rss|feed|atom)[^\s\"'<>]*", re.I)


def discover_source_candidates(limit: int = 200) -> int:
    """Discover candidate sources from recent documents.

    Example:
        `created_count = discover_source_candidates(limit=100)`
    """
    created_count = 0
    documents = NormalizedDocument.objects.select_related("source").all()[:limit]
    for document in documents:
        created_count += _discover_from_document(document)
    return created_count


def approve_discovery_candidate(candidate: DiscoveryCandidate) -> Source:
    """Approve a candidate by creating a disabled source row.

    Example:
        `source = approve_discovery_candidate(candidate)`
    """
    source, _created = Source.objects.update_or_create(
        name=candidate.name,
        defaults=_source_defaults(candidate),
    )
    candidate.status = DiscoveryCandidate.Status.APPROVED
    candidate.approved_at = timezone.now()
    candidate.save(update_fields=["status", "approved_at", "updated_at"])
    return source


def reject_discovery_candidate(candidate: DiscoveryCandidate) -> None:
    """Reject a candidate without deleting its evidence.

    Example:
        `reject_discovery_candidate(candidate)`
    """
    candidate.status = DiscoveryCandidate.Status.REJECTED
    candidate.rejected_at = timezone.now()
    candidate.save(update_fields=["status", "rejected_at", "updated_at"])


def _discover_from_document(document: NormalizedDocument) -> int:
    created = 0
    for url in _rss_urls_from_document(document):
        created += int(
            _create_candidate(
                document, DiscoveryCandidate.CandidateType.RSS, url, Decimal("0.80")
            )
        )
    created += int(
        _create_candidate(
            document,
            DiscoveryCandidate.CandidateType.DOMAIN,
            _domain_url(document),
            Decimal("0.45"),
        )
    )
    for entity in document.entities[:3]:
        created += int(_topic_candidate(document, str(entity)))
    return created


def _rss_urls_from_document(document: NormalizedDocument) -> tuple[str, ...]:
    urls = RSS_HINT_PATTERN.findall(
        " ".join([document.content, document.canonical_url])
    )
    return tuple(dict.fromkeys(url.strip(").,") for url in urls))


def _topic_candidate(document: NormalizedDocument, entity: str) -> bool:
    if len(entity.strip()) < 3:
        return False
    url = f"https://news.google.com/rss/search?q={entity.replace(' ', '+')}"
    return _create_candidate(
        document, DiscoveryCandidate.CandidateType.TOPIC, url, Decimal("0.50"), entity
    )


def _create_candidate(
    document: NormalizedDocument,
    candidate_type: str,
    url: str,
    confidence: Decimal,
    name: str | None = None,
) -> bool:
    candidate_name = name or _candidate_name(candidate_type, url)
    _candidate, created = DiscoveryCandidate.objects.get_or_create(
        candidate_type=candidate_type,
        url=url,
        defaults=_candidate_defaults(document, candidate_name, confidence),
    )
    return created


def _candidate_defaults(
    document: NormalizedDocument,
    name: str,
    confidence: Decimal,
) -> dict[str, object]:
    return {
        "name": name[:240],
        "evidence_url": document.canonical_url,
        "confidence": confidence,
        "category": document.source.category,
        "tags": document.tags,
    }


def _source_defaults(candidate: DiscoveryCandidate) -> dict[str, object]:
    return {
        "url": candidate.url,
        "source_type": _source_type(candidate),
        "fetch_method": Source.FetchMethod.HTTP,
        "category": candidate.category,
        "tags": candidate.tags,
        "is_enabled": False,
        "source_tier": 4,
        "reputation_score": 0,
    }


def _source_type(candidate: DiscoveryCandidate) -> str:
    if candidate.candidate_type in {
        DiscoveryCandidate.CandidateType.RSS,
        DiscoveryCandidate.CandidateType.TOPIC,
    }:
        return Source.SourceType.RSS
    return Source.SourceType.HTML


def _candidate_name(candidate_type: str, url: str) -> str:
    domain = urlsplit(url).netloc or url
    return f"Discovered {candidate_type}: {domain}"


def _domain_url(document: NormalizedDocument) -> str:
    parts = urlsplit(document.canonical_url)
    return f"{parts.scheme}://{parts.netloc}/"
