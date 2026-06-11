"""Auditable risk graph propagation over events, KG paths, and portfolios."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

import yaml

from sourceflow.events.impact_schema import default_event_impact
from sourceflow.kg import default_graph_store, node_ref

RISK_TYPES = frozenset(
    {
        "market_risk",
        "credit_risk",
        "liquidity_risk",
        "regulatory_risk",
        "legal_risk",
        "supply_chain_risk",
        "commodity_risk",
        "currency_risk",
        "country_risk",
        "sentiment_risk",
        "volatility_risk",
        "execution_risk",
    }
)
_CONFIDENCE_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class RiskRule:
    """Serializable risk propagation rule."""

    rule_id: str
    risk_type: str
    event_types: tuple[str, ...] = ()
    edge_types: tuple[str, ...] = ()
    weight: Decimal = Decimal("1")
    description: str = ""


@dataclass(frozen=True)
class RiskSignal:
    """One propagated risk signal with source evidence."""

    risk_type: str
    subject_type: str
    subject_id: str
    score: Decimal
    explanation: str
    graph_path: tuple[str, ...]
    source_evidence: tuple[Mapping[str, object], ...]
    rule_id: str
    assumptions_used: tuple[str, ...] = ("OWA",)


@dataclass(frozen=True)
class PortfolioRiskAggregate:
    """Aggregated portfolio risk signal."""

    portfolio_id: str
    risk_type: str
    score: Decimal
    contributors: tuple[RiskSignal, ...]
    explanation: str


class RiskGraph:
    """Propagate risk through canonical KG records."""

    def __init__(self, *, graph_store: object | None = None, rules: Iterable[RiskRule] | None = None) -> None:
        self.graph_store = graph_store or default_graph_store()
        self.rules = tuple(rules) if rules is not None else tuple(load_risk_rules())

    def propagate_event_risk(self, event: object) -> list[RiskSignal]:
        """Propagate direct risk from a negative event to actor and risk factors."""
        event_type = _value(event, "event_type") or "other"
        polarity = _value(event, "polarity") or "unknown"
        impact = default_event_impact(str(event_type), str(polarity))
        direction = Decimal("1") if polarity == "negative" else Decimal("0.40") if polarity == "unknown" else Decimal("0.20")
        signals: list[RiskSignal] = []
        for risk_type in impact.risk_channels:
            if risk_type not in RISK_TYPES:
                continue
            rule = _rule_for_event(self.rules, str(event_type), risk_type)
            score = _clamp(Decimal(str(_value(event, "confidence") or 0)) * direction * rule.weight)
            graph_path = (f"event:{_value(event, 'pk')} -has_actor-> entity:{_value(event, 'actor_entity_id')}",)
            signals.append(
                RiskSignal(
                    risk_type=risk_type,
                    subject_type="entity",
                    subject_id=str(_value(event, "actor_entity_id")),
                    score=score,
                    explanation=f"{polarity} {event_type} event increases {risk_type}",
                    graph_path=graph_path,
                    source_evidence=(_event_evidence(event),),
                    rule_id=rule.rule_id,
                )
            )
        return signals

    def propagate_supplier_customer_risk(self, base_signal: RiskSignal) -> list[RiskSignal]:
        """Propagate company risk through supplier/customer KG relations."""
        propagated: list[RiskSignal] = []
        if base_signal.subject_type != "entity":
            return propagated
        node = node_ref("entity", base_signal.subject_id)
        for neighbor in self.graph_store.get_neighbors(node, direction="both"):
            edge_type = _value(neighbor.edge, "edge_type")
            if edge_type not in {"supplies_to", "customer_of"} or neighbor.node.node_type != "entity":
                continue
            rule = _rule_for_edge(self.rules, edge_type, base_signal.risk_type)
            propagated.append(
                RiskSignal(
                    risk_type=base_signal.risk_type,
                    subject_type="entity",
                    subject_id=neighbor.node.node_id,
                    score=_clamp(base_signal.score * rule.weight * Decimal(str(_value(neighbor.edge, "confidence") or 1))),
                    explanation=f"{base_signal.risk_type} propagated through {edge_type} relation",
                    graph_path=(*base_signal.graph_path, _edge_text(neighbor.edge)),
                    source_evidence=base_signal.source_evidence,
                    rule_id=rule.rule_id,
                    assumptions_used=(*base_signal.assumptions_used, "supply_chain_relation_complete_under_PartialCWA"),
                )
            )
        return propagated

    def aggregate_portfolio_risk(
        self,
        portfolio_id: str,
        signals: Iterable[RiskSignal],
        *,
        positions: Iterable[object] = (),
    ) -> list[PortfolioRiskAggregate]:
        """Aggregate entity/asset risk signals by portfolio market exposure."""
        position_list = list(positions) or _portfolio_positions(portfolio_id)
        total_value = sum((abs(Decimal(str(_value(position, "market_value") or 0))) for position in position_list), Decimal("0"))
        exposures = _portfolio_entity_exposures(position_list, total_value)
        grouped: dict[str, list[RiskSignal]] = {}
        for signal in signals:
            if signal.subject_id not in exposures:
                continue
            weighted = RiskSignal(
                risk_type=signal.risk_type,
                subject_type="portfolio",
                subject_id=portfolio_id,
                score=_clamp(signal.score * exposures[signal.subject_id]),
                explanation=f"portfolio exposure aggregates {signal.explanation}",
                graph_path=(*signal.graph_path, f"portfolio:{portfolio_id} -holds-> exposed_entity:{signal.subject_id}"),
                source_evidence=signal.source_evidence,
                rule_id="portfolio_exposure_aggregation",
                assumptions_used=(*signal.assumptions_used, "portfolio_positions_controlled_CWA"),
            )
            grouped.setdefault(signal.risk_type, []).append(weighted)
        return [
            PortfolioRiskAggregate(
                portfolio_id=portfolio_id,
                risk_type=risk_type,
                score=_clamp(sum((signal.score for signal in contributors), Decimal("0"))),
                contributors=tuple(contributors),
                explanation=f"portfolio {portfolio_id} aggregate {risk_type}",
            )
            for risk_type, contributors in sorted(grouped.items())
        ]


def load_risk_rules(path: str | Path | None = None) -> list[RiskRule]:
    """Load auditable risk propagation rules from YAML."""
    rule_path = Path(path) if path else Path(__file__).with_name("risk_rules.yaml")
    loaded = yaml.safe_load(rule_path.read_text(encoding="utf-8")) or {}
    rules = loaded.get("rules", loaded if isinstance(loaded, list) else [])
    return [
        RiskRule(
            rule_id=str(rule.get("id") or rule.get("rule_id")),
            risk_type=str(rule.get("risk_type")),
            event_types=tuple(rule.get("event_types") or ()),
            edge_types=tuple(rule.get("edge_types") or ()),
            weight=Decimal(str(rule.get("weight", "1"))),
            description=str(rule.get("description", "")),
        )
        for rule in rules
    ]


def _rule_for_event(rules: tuple[RiskRule, ...], event_type: str, risk_type: str) -> RiskRule:
    for rule in rules:
        if rule.risk_type == risk_type and (not rule.event_types or event_type in rule.event_types):
            return rule
    return RiskRule("default_event_risk", risk_type, event_types=(event_type,))


def _rule_for_edge(rules: tuple[RiskRule, ...], edge_type: str, risk_type: str) -> RiskRule:
    for rule in rules:
        if rule.risk_type == risk_type and edge_type in rule.edge_types:
            return rule
    return RiskRule("default_relation_propagation", risk_type, edge_types=(edge_type,), weight=Decimal("0.50"))


def _portfolio_positions(portfolio_id: str) -> list[object]:
    from sourceflow.models import PortfolioPosition

    return list(PortfolioPosition.objects.select_related("asset").filter(portfolio_id=portfolio_id))


def _portfolio_entity_exposures(positions: list[object], total_value: Decimal) -> dict[str, Decimal]:
    exposures: dict[str, Decimal] = {}
    for position in positions:
        entity_id = _asset_entity_id(_value(position, "asset"))
        if not entity_id:
            continue
        weight = abs(Decimal(str(_value(position, "market_value") or 0))) / total_value if total_value else Decimal("0")
        exposures[str(entity_id)] = exposures.get(str(entity_id), Decimal("0")) + weight
    return exposures


def _asset_entity_id(asset: object) -> object:
    external_ids = _value(asset, "external_ids_json") or {}
    return external_ids.get("entity_id") if isinstance(external_ids, dict) else ""


def _event_evidence(event: object) -> dict[str, object]:
    evidence = _value(event, "evidence_span")
    source = _value(event, "source")
    return {
        "event_id": _value(event, "pk"),
        "source_id": _value(event, "source_id"),
        "source_name": _value(source, "name"),
        "document_id": _value(event, "document_id"),
        "evidence_span_id": _value(event, "evidence_span_id"),
        "evidence_text": _value(evidence, "text"),
    }


def _edge_text(edge: object) -> str:
    return f"{_value(edge, 'source_node_type')}:{_value(edge, 'source_node_id')} -{_value(edge, 'edge_type')}-> {_value(edge, 'target_node_type')}:{_value(edge, 'target_node_id')}"


def _clamp(value: Decimal) -> Decimal:
    return min(Decimal("1"), max(Decimal("0"), value)).quantize(_CONFIDENCE_QUANTUM)


def _value(record: object, key: str) -> object:
    return record.get(key, "") if isinstance(record, Mapping) else getattr(record, key, "")
