"""Convert structured events into testable alpha candidates."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Iterable, Mapping

from sourceflow.quant.alpha_hypotheses import AlphaCandidate

_CONFIDENCE_QUANTUM = Decimal("0.01")


def generate_event_alpha_candidates(
    events: Iterable[object],
    *,
    source_reliability_threshold: Decimal = Decimal("0.60"),
    sector_reactions: Mapping[str, Decimal | str | float] | None = None,
) -> list[AlphaCandidate]:
    """Generate testable alpha hypotheses from structured events."""
    candidates: list[AlphaCandidate] = []
    reactions = sector_reactions or {}
    for event in events:
        reliability = Decimal(str(_value(_value(event, "source"), "reliability_score") or 0))
        sector = _value(_value(event, "actor_entity"), "sector") or "unknown"
        sector_reaction = Decimal(str(reactions.get(str(sector), reactions.get("default", 0))))
        polarity = str(_value(event, "polarity") or "unknown")
        if reliability < source_reliability_threshold:
            continue
        if polarity == "negative" and sector_reaction <= 0:
            direction = "short"
            hypothesis = "negative reliable event with weak sector reaction predicts short-horizon abnormal underperformance"
        elif polarity == "positive" and sector_reaction >= 0:
            direction = "long"
            hypothesis = "positive reliable event with supportive sector reaction predicts short-horizon abnormal outperformance"
        else:
            continue
        event_id = str(_value(event, "pk") or _value(event, "id"))
        entity_id = str(_value(event, "actor_entity_id") or _value(_value(event, "actor_entity"), "pk"))
        confidence = _clamp((Decimal(str(_value(event, "confidence") or 0)) + reliability + min(abs(sector_reaction), Decimal("1"))) / Decimal("3"))
        candidates.append(
            AlphaCandidate(
                candidate_id=_candidate_id(event_id, direction, str(_value(event, "event_type"))),
                hypothesis=hypothesis,
                direction=direction,
                entry_horizon="next_open_to_1d",
                exit_horizon="5d_or_event_resolution",
                event_id=event_id,
                subject_entity_id=entity_id,
                confidence=confidence,
                reasoning_trail=(
                    {"step": "event", "event_id": event_id, "event_type": _value(event, "event_type"), "polarity": polarity},
                    {"step": "source_reliability", "value": str(reliability), "threshold": str(source_reliability_threshold)},
                    {"step": "sector_reaction", "sector": str(sector), "value": str(sector_reaction)},
                ),
                backtest_spec={
                    "test_type": "short_horizon_abnormal_return",
                    "benchmark": "sector_neutral",
                    "holding_period_days": 5,
                    "requires_no_live_trading": True,
                },
            )
        )
    return candidates


def _candidate_id(event_id: str, direction: str, event_type: str) -> str:
    digest = hashlib.sha1(f"{event_id}:{direction}:{event_type}".encode("utf-8")).hexdigest()[:12]
    return f"alpha_{digest}"


def _clamp(value: Decimal) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), value)).quantize(_CONFIDENCE_QUANTUM)


def _value(record: object, key: str) -> object:
    return record.get(key, "") if isinstance(record, dict) else getattr(record, key, "")
