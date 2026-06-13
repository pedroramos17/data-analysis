"""Portfolio risk and exposure explanation layer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

from sourceflow.quant.risk_graph import PortfolioRiskAggregate, RiskSignal


@dataclass(frozen=True)
class PortfolioRiskContribution:
    asset: str
    position: Mapping[str, object]
    risk_factors: tuple[str, ...]
    relevant_events: tuple[Mapping[str, object], ...]
    source_evidence: tuple[Mapping[str, object], ...]
    graph_paths: tuple[str, ...]
    suggested_hedge_candidates: tuple[str, ...]
    confidence: Decimal
    assumptions_used: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioExplanation:
    portfolio_id: str
    top_risk_contributors: tuple[PortfolioRiskContribution, ...]
    confidence: Decimal
    assumptions_used: tuple[str, ...]


def explain_portfolio_risk(
    portfolio_id: str,
    *,
    aggregates: Iterable[PortfolioRiskAggregate],
    positions: Iterable[object] = (),
    limit: int = 5,
) -> PortfolioExplanation:
    """Explain top portfolio risks using propagated risk signals."""
    position_map = {str(_asset_entity_id(_value(position, "asset"))): position for position in positions}
    contributions: list[PortfolioRiskContribution] = []
    for aggregate in aggregates:
        for signal in aggregate.contributors:
            source_entity_id = _extract_entity_id(signal)
            position = position_map.get(source_entity_id)
            contributions.append(
                PortfolioRiskContribution(
                    asset=_asset_label(_value(position, "asset")) if position else f"entity:{source_entity_id}",
                    position=_position_payload(position),
                    risk_factors=(signal.risk_type,),
                    relevant_events=tuple(evidence for evidence in signal.source_evidence if evidence.get("event_id")),
                    source_evidence=signal.source_evidence,
                    graph_paths=signal.graph_path,
                    suggested_hedge_candidates=_hedges(signal.risk_type),
                    confidence=signal.score,
                    assumptions_used=signal.assumptions_used,
                )
            )
    ordered = tuple(sorted(contributions, key=lambda item: item.confidence, reverse=True)[:limit])
    confidence = _average([item.confidence for item in ordered])
    assumptions = tuple(sorted({assumption for item in ordered for assumption in item.assumptions_used}))
    return PortfolioExplanation(portfolio_id=portfolio_id, top_risk_contributors=ordered, confidence=confidence, assumptions_used=assumptions)


def _extract_entity_id(signal: RiskSignal) -> str:
    for path in reversed(signal.graph_path):
        marker = "exposed_entity:"
        if marker in path:
            return path.split(marker, 1)[1]
    return signal.subject_id


def _hedges(risk_type: str) -> tuple[str, ...]:
    return {
        "currency_risk": ("currency_forward", "currency_hedged_etf"),
        "commodity_risk": ("commodity_future", "sector_pair_trade"),
        "market_risk": ("index_put_spread", "beta_reduction"),
        "liquidity_risk": ("position_size_reduction", "staggered_execution"),
        "legal_risk": ("reduce_single_name_exposure", "sector_neutral_pair"),
        "regulatory_risk": ("reduce_single_name_exposure", "policy_event_hedge"),
        "sentiment_risk": ("options_collar", "news_event_stop"),
    }.get(risk_type, ("position_size_reduction",))


def _position_payload(position: object | None) -> dict[str, object]:
    if position is None:
        return {}
    return {
        "portfolio_id": _value(position, "portfolio_id"),
        "asset_id": _value(position, "asset_id"),
        "quantity": str(_value(position, "quantity")),
        "market_value": str(_value(position, "market_value")),
        "currency": _value(position, "currency"),
    }


def _asset_label(asset: object) -> str:
    return str(_value(asset, "symbol") or _value(asset, "name") or "unknown_asset")


def _asset_entity_id(asset: object) -> object:
    external_ids = _value(asset, "external_ids_json") or {}
    return external_ids.get("entity_id") if isinstance(external_ids, dict) else ""


def _average(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return (sum(values, Decimal("0")) / len(values)).quantize(Decimal("0.01"))


def _value(record: object, key: str) -> object:
    return record.get(key, "") if isinstance(record, dict) else getattr(record, key, "")
