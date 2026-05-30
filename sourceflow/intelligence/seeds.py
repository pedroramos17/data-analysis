"""Seed symbolic factors for Sourceflow."""

from __future__ import annotations

from sourceflow.intelligence.factor_base.types import FactorDefinition
from sourceflow.intelligence.symbolic.expression import call, const, factor, operand
from sourceflow.intelligence.symbolic.grammar import OperandType


def seed_factor_definitions() -> tuple[FactorDefinition, ...]:
    """Return typed seed factor definitions.

    Example:
        `definitions = seed_factor_definitions()`
    """
    return (
        _coverage_intensity(),
        _provider_amplification(),
        _owner_amplification(),
        _omission_pressure(),
        _entity_omission(),
        _framing_divergence(),
        _provider_frame_concentration(),
        _claim_conflict(),
        _event_conflict_risk(),
        _amplified_conflict_risk(),
        _evidence_density(),
        _evidence_asymmetry(),
        _syndication_pressure(),
        _narrative_velocity(),
        _narrative_acceleration_shock(),
        _graph_spread(),
        _provider_dependency(),
        _coverage_uniqueness(),
    )


def _factor(
    name: str, description: str, expression: object, entity_type: str
) -> FactorDefinition:
    return FactorDefinition(name, description, expression, entity_type)


def _coverage_intensity() -> FactorDefinition:
    expr = call(
        "div",
        operand("article_count"),
        call("max", const(1), call("group_mean", operand("article_count"))),
    )
    return _factor(
        "coverage_intensity",
        "Compares source event coverage with its peer group.",
        expr,
        "source_event",
    )


def _provider_amplification() -> FactorDefinition:
    expr = call(
        "zscore_by_event",
        call(
            "div",
            operand("article_reach_weight"),
            call("max", const(1), call("group_sum", operand("article_reach_weight"))),
        ),
    )
    return _factor(
        "provider_amplification",
        "Measures provider share of event-weighted coverage.",
        expr,
        "provider_event",
    )


def _owner_amplification() -> FactorDefinition:
    expr = call(
        "zscore_by_event",
        call(
            "div",
            operand("article_reach_weight"),
            call("max", const(1), call("group_sum", operand("article_reach_weight"))),
        ),
    )
    return _factor(
        "owner_amplification",
        "Measures owner share of event-weighted coverage.",
        expr,
        "owner_event",
    )


def _omission_pressure() -> FactorDefinition:
    expr = call(
        "max",
        const(0),
        call(
            "sub",
            call("group_median", operand("claim_coverage")),
            operand("claim_coverage"),
        ),
    )
    return _factor(
        "omission_pressure",
        "Compares source claim coverage against peers.",
        expr,
        "source_event",
    )


def _entity_omission() -> FactorDefinition:
    expr = call(
        "max",
        const(0),
        call(
            "sub",
            call("group_median", operand("claim_coverage")),
            operand("claim_coverage"),
        ),
    )
    return _factor(
        "entity_omission",
        "Measures source omission of entities covered by peers.",
        expr,
        "source_entity_event",
    )


def _framing_divergence() -> FactorDefinition:
    expr = call(
        "js_divergence",
        operand("frame_distribution", OperandType.DISTRIBUTION),
        operand("frame_distribution", OperandType.DISTRIBUTION),
    )
    return _factor(
        "framing_divergence",
        "Compares source framing distribution with event framing.",
        expr,
        "source_event",
    )


def _provider_frame_concentration() -> FactorDefinition:
    expr = call(
        "frame_entropy", operand("frame_distribution", OperandType.DISTRIBUTION)
    )
    return _factor(
        "provider_frame_concentration",
        "Measures provider concentration around a frame.",
        expr,
        "provider_event",
    )


def _claim_conflict() -> FactorDefinition:
    expr = call(
        "add",
        call(
            "stance_entropy", operand("stance_distribution", OperandType.DISTRIBUTION)
        ),
        call(
            "add",
            call("log1p", operand("contradiction_edge_count")),
            operand("disagreement_provider_diversity"),
        ),
    )
    return _factor(
        "claim_conflict",
        "Scores claim disagreement across providers.",
        expr,
        "claim_event",
    )


def _event_conflict_risk() -> FactorDefinition:
    expr = call(
        "mul",
        call("zscore", call("group_sum", factor("claim_conflict"))),
        call(
            "mul",
            call("log1p", operand("event_source_count")),
            call(
                "frame_entropy", operand("frame_distribution", OperandType.DISTRIBUTION)
            ),
        ),
    )
    return _factor(
        "event_conflict_risk",
        "Aggregates claim conflict with source spread and frame entropy.",
        expr,
        "event",
    )


def _amplified_conflict_risk() -> FactorDefinition:
    expr = call(
        "mul",
        factor("event_conflict_risk"),
        call(
            "mul",
            factor("provider_amplification"),
            factor("provider_frame_concentration"),
        ),
    )
    return _factor(
        "amplified_conflict_risk",
        "Combines conflict risk with provider amplification and frame concentration.",
        expr,
        "event",
    )


def _evidence_density() -> FactorDefinition:
    expr = call(
        "div",
        operand("evidence_span_count"),
        call("max", const(1), operand("article_count")),
    )
    return _factor(
        "evidence_density",
        "Compares evidence spans per article for a source and event.",
        expr,
        "source_event",
    )


def _evidence_asymmetry() -> FactorDefinition:
    expr = call(
        "abs",
        call(
            "sub",
            operand("evidence_span_count"),
            call("group_mean", operand("evidence_span_count")),
        ),
    )
    return _factor(
        "evidence_asymmetry",
        "Measures evidence density difference from event peers.",
        expr,
        "source_event",
    )


def _syndication_pressure() -> FactorDefinition:
    expr = call("log1p", operand("syndication_edge_count"))
    return _factor(
        "syndication_pressure",
        "Measures provider-level repetition pressure.",
        expr,
        "provider_event",
    )


def _narrative_velocity() -> FactorDefinition:
    expr = call("div", operand("article_count"), const(24))
    return _factor(
        "narrative_velocity",
        "Measures event coverage speed in the window.",
        expr,
        "event",
    )


def _narrative_acceleration_shock() -> FactorDefinition:
    expr = call("abs", call("rolling_delta", factor("narrative_velocity")))
    return _factor(
        "narrative_acceleration_shock",
        "Measures sudden narrative velocity changes.",
        expr,
        "event",
    )


def _graph_spread() -> FactorDefinition:
    expr = call("log1p", operand("graph_degree"))
    return _factor(
        "graph_spread",
        "Measures event spread in the source-provider-entity graph.",
        expr,
        "event",
    )


def _provider_dependency() -> FactorDefinition:
    expr = call(
        "div",
        operand("article_count"),
        call("max", const(1), call("group_sum", operand("article_count"))),
    )
    return _factor(
        "provider_dependency",
        "Measures source dependence on provider event volume.",
        expr,
        "source_event",
    )


def _coverage_uniqueness() -> FactorDefinition:
    expr = call(
        "div",
        const(1),
        call("max", const(1), call("group_sum", operand("article_count"))),
    )
    return _factor(
        "coverage_uniqueness",
        "Measures how unique a source's event coverage is.",
        expr,
        "source_event",
    )
