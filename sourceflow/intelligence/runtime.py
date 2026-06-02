"""Runtime orchestration for seed symbolic factor computation."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

from sourceflow.intelligence.factor_base.dag import schedule_factor_computation
from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.factor_base.storage import FactorValueStorage
from sourceflow.intelligence.meta_factors.articles import article_event_rows
from sourceflow.intelligence.meta_factors.claims import (
    claim_event_rows,
    contradiction_counts,
)
from sourceflow.intelligence.meta_factors.common import MetaFactorContext
from sourceflow.intelligence.meta_factors.entities import entity_event_rows
from sourceflow.intelligence.meta_factors.evidence import evidence_rows
from sourceflow.intelligence.meta_factors.frames import frame_rows
from sourceflow.intelligence.meta_factors.graph_metrics import graph_metric_rows
from sourceflow.intelligence.seeds import seed_factor_definitions


def compute_seed_factor_values(
    connection: object,
    output_dir: Path,
    as_of: datetime,
    history_start: datetime,
    history_end: datetime,
) -> dict[str, Path]:
    """Compute all seed factors and persist values to Parquet.

    Example:
        `compute_seed_factor_values(connection, Path("exports"), now, start, end)`
    """
    registry = FactorRegistry(connection)
    definitions = schedule_factor_computation(seed_factor_definitions())
    registry.register_factors(definitions)
    context = MetaFactorContext(as_of, history_start, history_end)
    factor_rows = build_seed_factor_rows(context)
    return _persist_factor_rows(registry, output_dir / "factors", as_of, factor_rows)


def build_seed_factor_rows(
    context: MetaFactorContext,
) -> dict[str, list[dict[str, object]]]:
    """Build all seed factor value rows for a context.

    Example:
        `rows = build_seed_factor_rows(context)`
    """
    articles = article_event_rows(context)
    claims = claim_event_rows(context)
    frames = frame_rows(context)
    evidence = evidence_rows(context)
    graph_rows = graph_metric_rows(context)
    return _all_factor_rows(context, articles, claims, frames, evidence, graph_rows)


def _all_factor_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
    claims: list[dict[str, object]],
    frames: list[dict[str, object]],
    evidence: list[dict[str, object]],
    graph_rows: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    rows = _base_factor_rows(context, articles, claims, frames, evidence)
    rows["claim_conflict"] = _claim_conflict_rows(context, claims)
    rows["event_conflict_risk"] = _event_conflict_rows(context, rows, frames, articles)
    rows["amplified_conflict_risk"] = _amplified_risk_rows(context, rows)
    rows["graph_spread"] = _graph_spread_rows(context, graph_rows)
    rows["narrative_acceleration_shock"] = _shock_rows(context, rows)
    return rows


def _base_factor_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
    claims: list[dict[str, object]],
    frames: list[dict[str, object]],
    evidence: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    counts = _source_event_counts(articles)
    rows: dict[str, list[dict[str, object]]] = {}
    rows["coverage_intensity"] = _coverage_rows(context, articles, counts)
    rows["provider_amplification"] = _group_amplification_rows(
        context, articles, "provider"
    )
    rows["owner_amplification"] = _group_amplification_rows(context, articles, "owner")
    rows["omission_pressure"] = _omission_rows(context, articles, counts)
    rows["entity_omission"] = _entity_omission_rows(context)
    rows["framing_divergence"] = _framing_rows(context, frames)
    rows["provider_frame_concentration"] = _provider_frame_rows(context, frames)
    rows["evidence_density"] = _evidence_density_rows(context, evidence, counts)
    rows["evidence_asymmetry"] = _evidence_asymmetry_rows(
        context, rows["evidence_density"]
    )
    rows["syndication_pressure"] = _syndication_rows(context, articles)
    rows["narrative_velocity"] = _velocity_rows(context, articles)
    rows["provider_dependency"] = _provider_dependency_rows(context, articles, counts)
    rows["coverage_uniqueness"] = _coverage_unique_rows(context, articles)
    return rows


def _persist_factor_rows(
    registry: FactorRegistry,
    output_dir: Path,
    as_of: datetime,
    factor_rows: dict[str, list[dict[str, object]]],
) -> dict[str, Path]:
    storage = FactorValueStorage(output_dir)
    paths: dict[str, Path] = {}
    for factor_name, rows in factor_rows.items():
        path = storage.write_values(factor_name, rows)
        registry.record_factor_values(factor_name, as_of, path, len(rows))
        paths[factor_name] = path
    return paths


def _source_event_counts(
    articles: list[dict[str, object]],
) -> Counter[tuple[int, int]]:
    return Counter((int(row["source_id"]), int(row["event_id"])) for row in articles)


def _coverage_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
    counts: Counter[tuple[int, int]],
) -> list[dict[str, object]]:
    peer_counts = _peer_counts_by_event(articles, counts)
    rows = []
    for source_event, article_count in counts.items():
        source_id, event_id = source_event
        peer_mean = mean(peer_counts[event_id]) if peer_counts[event_id] else 1
        rows.append(
            _row(
                "coverage_intensity",
                context,
                event_id,
                source_id,
                article_count / max(1, peer_mean),
            )
        )
    return rows


def _group_amplification_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
    group_key: str,
) -> list[dict[str, object]]:
    grouped = _group_event_weights(articles, group_key)
    totals = _event_totals(grouped)
    shares = [
        (key, event_id, weight / max(1, totals[event_id]))
        for (key, event_id), weight in grouped.items()
    ]
    return [
        _group_row(
            f"{group_key}_amplification",
            context,
            event_id,
            key,
            _zscore_value(value, shares, event_id),
        )
        for key, event_id, value in shares
    ]


def _omission_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
    counts: Counter[tuple[int, int]],
) -> list[dict[str, object]]:
    peer_counts = _peer_counts_by_event(articles, counts)
    rows = []
    for (source_id, event_id), article_count in counts.items():
        pressure = max(0.0, median(peer_counts[event_id]) - article_count)
        rows.append(_row("omission_pressure", context, event_id, source_id, pressure))
    return rows


def _entity_omission_rows(context: MetaFactorContext) -> list[dict[str, object]]:
    counts = Counter(
        (row["source_id"], row["event_id"], row["entity"])
        for row in entity_event_rows(context)
    )
    entity_groups = _entity_event_values(counts)
    return [
        _entity_row(context, source_id, event_id, entity, value)
        for (source_id, event_id, entity), value in entity_groups.items()
    ]


def _framing_rows(
    context: MetaFactorContext,
    frames: list[dict[str, object]],
) -> list[dict[str, object]]:
    source_dist = _frame_distributions(frames, ("source_id", "event_id"))
    event_dist = _frame_distributions(frames, ("event_id",))
    return [
        _row(
            "framing_divergence",
            context,
            event_id,
            source_id,
            _js(source_dist[key], event_dist[(event_id,)]),
        )
        for key, (source_id, event_id) in _source_event_keys(source_dist)
    ]


def _provider_frame_rows(
    context: MetaFactorContext,
    frames: list[dict[str, object]],
) -> list[dict[str, object]]:
    distributions = _frame_distributions(frames, ("provider", "event_id"))
    return [
        _group_row(
            "provider_frame_concentration", context, key[1], key[0], _max_share(dist)
        )
        for key, dist in distributions.items()
    ]


def _evidence_density_rows(
    context: MetaFactorContext,
    evidence: list[dict[str, object]],
    counts: Counter[tuple[int, int]],
) -> list[dict[str, object]]:
    spans = Counter()
    for row in evidence:
        spans[(int(row["source_id"]), int(row["event_id"]))] += int(
            row["evidence_span_count"]
        )
    return [
        _row(
            "evidence_density",
            context,
            event_id,
            source_id,
            spans[(source_id, event_id)] / max(1, count),
        )
        for (source_id, event_id), count in counts.items()
    ]


def _evidence_asymmetry_rows(
    context: MetaFactorContext,
    density_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    event_values = _values_by_event(density_rows)
    return [
        _row(
            "evidence_asymmetry",
            context,
            int(row["event_id"]),
            int(row["source_id"]),
            abs(float(row["value"]) - mean(event_values[int(row["event_id"])])),
        )
        for row in density_rows
    ]


def _syndication_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
) -> list[dict[str, object]]:
    grouped = Counter((row["provider"], row["event_id"]) for row in articles)
    return [
        _group_row(
            "syndication_pressure",
            context,
            int(event_id),
            str(provider),
            math.log1p(count),
        )
        for (provider, event_id), count in grouped.items()
    ]


def _velocity_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
) -> list[dict[str, object]]:
    event_counts = Counter(int(row["event_id"]) for row in articles)
    hours = max(
        1.0, (context.history_end - context.history_start).total_seconds() / 3600
    )
    return [
        _event_row("narrative_velocity", context, event_id, count / hours)
        for event_id, count in event_counts.items()
    ]


def _provider_dependency_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
    counts: Counter[tuple[int, int]],
) -> list[dict[str, object]]:
    provider_totals = Counter((row["provider"], row["event_id"]) for row in articles)
    providers = _provider_by_source_event(articles)
    return [
        _row(
            "provider_dependency",
            context,
            event_id,
            source_id,
            count
            / max(1, provider_totals[(providers[(source_id, event_id)], event_id)]),
        )
        for (source_id, event_id), count in counts.items()
    ]


def _coverage_unique_rows(
    context: MetaFactorContext,
    articles: list[dict[str, object]],
) -> list[dict[str, object]]:
    provider_counts = Counter((row["provider"], row["event_id"]) for row in articles)
    return [
        _row(
            "coverage_uniqueness",
            context,
            int(row["event_id"]),
            int(row["source_id"]),
            1 / max(1, provider_counts[(row["provider"], row["event_id"])]),
        )
        for row in articles
    ]


def _claim_conflict_rows(
    context: MetaFactorContext,
    claims: list[dict[str, object]],
) -> list[dict[str, object]]:
    contradictions = contradiction_counts(context)
    grouped = _claim_groups(claims)
    return [
        _claim_row(
            context,
            claim,
            event_id,
            _claim_conflict_value(providers, contradictions.get((claim, event_id), 0)),
        )
        for (claim, event_id), providers in grouped.items()
    ]


def _event_conflict_rows(
    context: MetaFactorContext,
    rows: dict[str, list[dict[str, object]]],
    frames: list[dict[str, object]],
    articles: list[dict[str, object]],
) -> list[dict[str, object]]:
    claim_sums = _sum_by_event(rows["claim_conflict"])
    source_counts = Counter(int(row["event_id"]) for row in articles)
    frame_entropy = _event_frame_entropy(frames)
    return [
        _event_row(
            "event_conflict_risk",
            context,
            event_id,
            value
            * math.log1p(source_counts[event_id])
            * frame_entropy.get(event_id, 0),
        )
        for event_id, value in claim_sums.items()
    ]


def _amplified_risk_rows(
    context: MetaFactorContext,
    rows: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    event_risk = {
        int(row["event_id"]): float(row["value"]) for row in rows["event_conflict_risk"]
    }
    max_provider = _max_by_event(rows["provider_amplification"])
    max_frame = _max_by_event(rows["provider_frame_concentration"])
    return [
        _event_row(
            "amplified_conflict_risk",
            context,
            event_id,
            value * max_provider.get(event_id, 0) * max_frame.get(event_id, 0),
        )
        for event_id, value in event_risk.items()
    ]


def _graph_spread_rows(
    context: MetaFactorContext,
    graph_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        _event_row(
            "graph_spread",
            context,
            int(row["event_id"]),
            math.log1p(float(row["graph_degree"])),
        )
        for row in graph_rows
    ]


def _shock_rows(
    context: MetaFactorContext,
    rows: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    return [
        _event_row(
            "narrative_acceleration_shock",
            context,
            int(row["event_id"]),
            abs(float(row["value"])),
        )
        for row in rows["narrative_velocity"]
    ]


def _row(
    factor_name: str,
    context: MetaFactorContext,
    event_id: int,
    source_id: int,
    value: float,
) -> dict[str, object]:
    return {
        "factor_name": factor_name,
        "entity_id": f"source:{source_id}|event:{event_id}",
        "event_id": event_id,
        "source_id": source_id,
        "as_of": context.as_of,
        "value": float(value),
    }


def _group_row(
    factor_name: str,
    context: MetaFactorContext,
    event_id: int,
    key: str,
    value: float,
) -> dict[str, object]:
    return {
        "factor_name": factor_name,
        "entity_id": f"{key}|event:{event_id}",
        "event_id": event_id,
        "source_id": None,
        "as_of": context.as_of,
        "value": float(value),
        "group_key": key,
    }


def _event_row(
    factor_name: str,
    context: MetaFactorContext,
    event_id: int,
    value: float,
) -> dict[str, object]:
    return {
        "factor_name": factor_name,
        "entity_id": f"event:{event_id}",
        "event_id": event_id,
        "source_id": None,
        "as_of": context.as_of,
        "value": float(value),
    }


def _claim_row(
    context: MetaFactorContext,
    claim: str,
    event_id: int,
    value: float,
) -> dict[str, object]:
    return {
        "factor_name": "claim_conflict",
        "entity_id": f"claim:{claim}|event:{event_id}",
        "event_id": event_id,
        "source_id": None,
        "as_of": context.as_of,
        "value": float(value),
        "claim": claim,
    }


def _entity_row(
    context: MetaFactorContext,
    source_id: int,
    event_id: int,
    entity: str,
    value: float,
) -> dict[str, object]:
    return {
        "factor_name": "entity_omission",
        "entity_id": f"source:{source_id}|entity:{entity}|event:{event_id}",
        "event_id": event_id,
        "source_id": source_id,
        "as_of": context.as_of,
        "value": float(value),
        "entity": entity,
    }


def _peer_counts_by_event(
    articles: list[dict[str, object]],
    counts: Counter[tuple[int, int]],
) -> dict[int, list[int]]:
    peers: dict[int, list[int]] = defaultdict(list)
    for source_id, event_id in counts:
        peers[event_id].append(counts[(source_id, event_id)])
    return peers


def _group_event_weights(
    articles: list[dict[str, object]],
    group_key: str,
) -> Counter[tuple[str, int]]:
    weights: Counter[tuple[str, int]] = Counter()
    for row in articles:
        weights[(str(row[group_key]), int(row["event_id"]))] += float(
            row["article_reach_weight"]
        )
    return weights


def _event_totals(grouped: Counter[tuple[str, int]]) -> Counter[int]:
    totals: Counter[int] = Counter()
    for (_key, event_id), value in grouped.items():
        totals[event_id] += value
    return totals


def _zscore_value(
    value: float,
    shares: list[tuple[str, int, float]],
    event_id: int,
) -> float:
    event_values = [
        share for _key, row_event_id, share in shares if row_event_id == event_id
    ]
    std = _std(event_values)
    return 0.0 if std == 0 else (value - mean(event_values)) / std


def _entity_event_values(
    counts: Counter[tuple[int, int, str]],
) -> dict[tuple[int, int, str], float]:
    grouped: dict[tuple[int, str], list[int]] = defaultdict(list)
    for (_source_id, event_id, entity), count in counts.items():
        grouped[(event_id, entity)].append(count)
    return {
        key: max(0.0, median(grouped[(key[1], key[2])]) - value)
        for key, value in counts.items()
    }


def _frame_distributions(
    frames: list[dict[str, object]],
    keys: tuple[str, ...],
) -> dict[tuple[object, ...], dict[str, float]]:
    counts: dict[tuple[object, ...], Counter[str]] = defaultdict(Counter)
    for row in frames:
        key = tuple(row[name] for name in keys)
        counts[key][str(row["frame"])] += 1
    return {key: _normalized(counter) for key, counter in counts.items()}


def _source_event_keys(
    distributions: dict[tuple[object, ...], dict[str, float]],
) -> list[tuple[tuple[object, ...], tuple[int, int]]]:
    return [(key, (int(key[0]), int(key[1]))) for key in distributions]


def _normalized(counter: Counter[str]) -> dict[str, float]:
    total = max(1, sum(counter.values()))
    return {key: value / total for key, value in counter.items()}


def _js(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    middle = {key: (left.get(key, 0) + right.get(key, 0)) / 2 for key in keys}
    return (_kl(left, middle) + _kl(right, middle)) / 2


def _kl(left: dict[str, float], right: dict[str, float]) -> float:
    return sum(
        value * math.log(value / max(right.get(key, 1e-9), 1e-9))
        for key, value in left.items()
        if value > 0
    )


def _max_share(distribution: dict[str, float]) -> float:
    return max(distribution.values()) if distribution else 0.0


def _values_by_event(rows: list[dict[str, object]]) -> dict[int, list[float]]:
    values: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        values[int(row["event_id"])].append(float(row["value"]))
    return values


def _provider_by_source_event(
    articles: list[dict[str, object]],
) -> dict[tuple[int, int], str]:
    return {
        (int(row["source_id"]), int(row["event_id"])): str(row["provider"])
        for row in articles
    }


def _claim_groups(
    claims: list[dict[str, object]],
) -> dict[tuple[str, int], set[str]]:
    groups: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in claims:
        groups[(str(row["claim"]), int(row["event_id"]))].add(str(row["provider"]))
    return groups


def _claim_conflict_value(providers: set[str], contradictions: int) -> float:
    diversity = len(providers) / max(1, len(providers) + 1)
    return diversity + math.log1p(contradictions)


def _sum_by_event(rows: list[dict[str, object]]) -> Counter[int]:
    values: Counter[int] = Counter()
    for row in rows:
        values[int(row["event_id"])] += float(row["value"])
    return values


def _event_frame_entropy(frames: list[dict[str, object]]) -> dict[int, float]:
    distributions = _frame_distributions(frames, ("event_id",))
    return {int(key[0]): _entropy(value) for key, value in distributions.items()}


def _entropy(distribution: dict[str, float]) -> float:
    return -sum(value * math.log(max(value, 1e-9)) for value in distribution.values())


def _max_by_event(rows: list[dict[str, object]]) -> dict[int, float]:
    values: dict[int, float] = defaultdict(float)
    for row in rows:
        values[int(row["event_id"])] = max(
            values[int(row["event_id"])], float(row["value"])
        )
    return dict(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))
