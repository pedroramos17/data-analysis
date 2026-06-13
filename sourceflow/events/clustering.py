"""Event clustering helpers for source comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable


@dataclass(frozen=True)
class EventCluster:
    """A cluster of events and claims describing the same market event."""

    cluster_id: str
    key: str
    events: tuple[object, ...]
    claims: tuple[object, ...] = ()
    subject_ids: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    object_keys: tuple[str, ...] = ()
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


def event_cluster_key(event: object) -> str:
    """Return a stable key for grouping similar canonical events."""
    actor_id = str(_value(event, "actor_entity_id") or _value(event, "actor_id") or _entity_id(_value(event, "actor_entity")))
    event_type = _normalize(_value(event, "event_type") or "other")
    object_key = _object_key(event)
    return f"actor:{actor_id}|type:{event_type}|object:{object_key}"


def cluster_events(events: Iterable[object], *, claims: Iterable[object] = ()) -> list[EventCluster]:
    """Cluster events by actor, event type, and object text/entity."""
    grouped: dict[str, list[object]] = {}
    for event in events:
        grouped.setdefault(event_cluster_key(event), []).append(event)
    claim_list = tuple(claims)
    clusters: list[EventCluster] = []
    for index, (key, members) in enumerate(sorted(grouped.items()), start=1):
        documents = {_value(event, "document_id") for event in members if _value(event, "document_id")}
        actor_ids = {str(_value(event, "actor_entity_id") or _entity_id(_value(event, "actor_entity"))) for event in members}
        cluster_claims = tuple(
            claim
            for claim in claim_list
            if _value(claim, "document_id") in documents
            or str(_value(claim, "subject_entity_id") or _entity_id(_value(claim, "subject_entity"))) in actor_ids
        )
        seen_times = [time for time in (_event_time(event) for event in members) if time is not None]
        clusters.append(
            EventCluster(
                cluster_id=f"event_cluster_{index}",
                key=key,
                events=tuple(members),
                claims=cluster_claims,
                subject_ids=tuple(sorted(actor_ids)),
                event_types=tuple(sorted({_normalize(_value(event, "event_type") or "other") for event in members})),
                object_keys=tuple(sorted({_object_key(event) for event in members})),
                first_seen_at=min(seen_times) if seen_times else None,
                last_seen_at=max(seen_times) if seen_times else None,
            )
        )
    return clusters


def _event_time(event: object) -> datetime | None:
    return _value(event, "event_time") or _value(event, "created_at")


def _object_key(event: object) -> str:
    object_entity_id = _value(event, "object_entity_id") or _entity_id(_value(event, "object_entity"))
    if object_entity_id:
        return f"entity:{object_entity_id}"
    return f"literal:{_normalize(_value(event, 'object_literal') or _value(event, 'object'))}"


def _entity_id(entity: object) -> object:
    return _value(entity, "pk") or _value(entity, "id") if entity else ""


def _normalize(value: object) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", str(value).lower())) or "unknown"


def _value(record: object, key: str) -> object:
    return record.get(key, "") if isinstance(record, dict) else getattr(record, key, "")
