"""Typed grammar for symbolic factor formulas."""

from __future__ import annotations

from dataclasses import dataclass

from sourceflow.intelligence.symbolic.types import ObjectLevel, OperatorKind, ReturnType

OperandType = ReturnType


@dataclass(frozen=True, slots=True)
class OperandSpec:
    """Typed metadata for one formula operand.

    Example:
        `OperandSpec("article_count", ReturnType.NUMERIC)`
    """

    name: str
    return_type: ReturnType
    object_level: ObjectLevel = ObjectLevel.EVENT
    future_only: bool = False

    @property
    def operand_type(self) -> ReturnType:
        """Return legacy operand type alias.

        Example:
            `spec.operand_type`
        """
        return self.return_type


@dataclass(frozen=True, slots=True)
class OperatorSpec:
    """Typed metadata for one symbolic operator.

    Example:
        `OperatorSpec("log1p", OperatorKind.ELEMENT, numeric_args, numeric)`
    """

    name: str
    kind: OperatorKind
    argument_types: tuple[ReturnType, ...]
    return_type: ReturnType
    future_only: bool = False


def operand_specs() -> dict[str, OperandSpec]:
    """Return all built-in operand specs.

    Example:
        `specs = operand_specs()`
    """
    specs = _raw_operand_specs() + _factor_operand_specs() + _future_operand_specs()
    return {spec.name: spec for spec in specs}


def operator_specs() -> dict[str, OperatorSpec]:
    """Return all built-in operator specs.

    Example:
        `specs = operator_specs()`
    """
    specs = []
    specs.extend(_element_specs())
    specs.extend(_time_series_specs())
    specs.extend(_group_specs())
    specs.extend(_post_process_specs())
    specs.extend(_distribution_specs())
    specs.extend(_set_specs())
    specs.extend(_graph_specs())
    specs.extend(_future_operator_specs())
    return {spec.name: spec for spec in specs}


def resolve_operand_type(name: str) -> ReturnType:
    """Return the configured type for an operand name.

    Example:
        `resolve_operand_type("article_count")`
    """
    spec = operand_specs().get(name)
    return spec.return_type if spec else ReturnType.UNKNOWN


def resolve_operator(name: str) -> OperatorSpec:
    """Return the operator spec or raise a typed error.

    Example:
        `resolve_operator("log1p")`
    """
    spec = operator_specs().get(name)
    if spec is None:
        raise ValueError(f"Invalid operator {name}; expected registered operator")
    return spec


def numeric_operand_names() -> tuple[str, ...]:
    """Return numeric raw operands used by formula search.

    Example:
        `names = numeric_operand_names()`
    """
    return tuple(
        spec.name
        for spec in operand_specs().values()
        if spec.return_type == ReturnType.NUMERIC and not spec.future_only
    )


def factor_operand_names() -> tuple[str, ...]:
    """Return seed factor names available to random search.

    Example:
        `names = factor_operand_names()`
    """
    return tuple(spec.name for spec in _factor_operand_specs())


def _raw_operand_specs() -> tuple[OperandSpec, ...]:
    numeric = _numeric_specs()
    distributions = _distribution_operand_specs()
    sets = _set_operand_specs()
    graph_nodes = _graph_node_specs()
    return numeric + distributions + sets + graph_nodes


def _numeric_specs() -> tuple[OperandSpec, ...]:
    names = (
        "article_count",
        "article_reach_weight",
        "provider_article_count",
        "owner_article_count",
        "event_article_count",
        "event_source_count",
        "event_provider_count",
        "event_claim_count",
        "event_entity_count",
        "claim_frequency",
        "claim_coverage",
        "contradiction_edge_count",
        "stance_entropy",
        "disagreement_provider_diversity",
        "evidence_span_count",
        "quote_count",
        "entity_presence",
        "entity_salience_global",
        "syndication_edge_count",
        "graph_degree",
        "graph_pagerank",
        "graph_bridge_score",
        "graph_spread",
    )
    return tuple(OperandSpec(name, ReturnType.NUMERIC) for name in names)


def _distribution_operand_specs() -> tuple[OperandSpec, ...]:
    names = (
        "frame_distribution",
        "event_frame_distribution",
        "provider_frame_distribution",
        "stance_distribution",
        "provider_distribution",
    )
    return tuple(OperandSpec(name, ReturnType.DISTRIBUTION) for name in names)


def _set_operand_specs() -> tuple[OperandSpec, ...]:
    names = ("entity_set", "claim_set", "source_set")
    return tuple(OperandSpec(name, ReturnType.SET) for name in names)


def _graph_node_specs() -> tuple[OperandSpec, ...]:
    names = ("entity_node", "source_node", "provider_node", "event_node")
    return tuple(OperandSpec(name, ReturnType.GRAPH_NODE) for name in names)


def _factor_operand_specs() -> tuple[OperandSpec, ...]:
    names = (
        "coverage_intensity",
        "provider_amplification",
        "owner_amplification",
        "omission_pressure",
        "entity_omission",
        "framing_divergence",
        "claim_conflict",
        "event_conflict_risk",
        "amplified_conflict_risk",
        "evidence_density",
        "evidence_asymmetry",
        "syndication_pressure",
        "narrative_velocity",
        "narrative_acceleration_shock",
        "graph_spread",
        "provider_dependency",
        "coverage_uniqueness",
    )
    return tuple(OperandSpec(name, ReturnType.FACTOR) for name in names)


def _future_operand_specs() -> tuple[OperandSpec, ...]:
    names = (
        "future_event_growth",
        "future_provider_spread",
        "future_claim_conflict",
        "alert_feedback",
        "analyst_feedback",
        "retrieval_value",
    )
    return tuple(
        OperandSpec(name, ReturnType.NUMERIC, future_only=True) for name in names
    )


def _element_specs() -> tuple[OperatorSpec, ...]:
    binary = ("add", "sub", "mul", "div", "div_safe", "max", "min")
    unary = ("log1p", "sqrt", "abs", "neg", "sigmoid")
    specs = [_operator(name, OperatorKind.ELEMENT, _two_numeric()) for name in binary]
    specs.extend(
        _operator(name, OperatorKind.ELEMENT, _one_numeric()) for name in unary
    )
    specs.append(_operator("clip", OperatorKind.ELEMENT, _one_numeric()))
    return tuple(specs)


def _time_series_specs() -> tuple[OperatorSpec, ...]:
    names = (
        "ts_sum",
        "ts_mean",
        "ts_std",
        "ts_zscore",
        "ts_rank",
        "ts_delta",
        "ts_slope",
        "ts_accel",
        "ts_decay_linear",
        "rolling_delta",
    )
    specs = [
        _operator(name, OperatorKind.TIME_SERIES, _one_numeric()) for name in names
    ]
    specs.append(_operator("ts_corr", OperatorKind.TIME_SERIES, _two_numeric()))
    return tuple(specs)


def _group_specs() -> tuple[OperatorSpec, ...]:
    names = (
        "group_mean",
        "group_sum",
        "group_std",
        "group_rank",
        "group_share",
        "group_entropy",
        "group_topk_share",
        "group_median",
    )
    return tuple(_operator(name, OperatorKind.GROUP, _one_numeric()) for name in names)


def _post_process_specs() -> tuple[OperatorSpec, ...]:
    names = (
        "rank",
        "percentile",
        "zscore",
        "zscore_by_event",
        "winsorize",
        "standardize_by_event",
        "standardize_by_source",
        "neutralize_by_provider",
        "neutralize_by_language",
        "neutralize_by_article_volume",
        "smooth",
    )
    return tuple(
        _operator(name, OperatorKind.POST_PROCESS, _one_numeric()) for name in names
    )


def _distribution_specs() -> tuple[OperatorSpec, ...]:
    return (
        _operator("entropy", OperatorKind.DISTRIBUTION, (ReturnType.DISTRIBUTION,)),
        _operator("gini", OperatorKind.DISTRIBUTION, (ReturnType.DISTRIBUTION,)),
        _operator("js_divergence", OperatorKind.DISTRIBUTION, _two_distributions()),
        _operator("kl_divergence", OperatorKind.DISTRIBUTION, _two_distributions()),
        _operator("cosine_sim", OperatorKind.DISTRIBUTION, _two_distributions()),
        _operator(
            "stance_entropy", OperatorKind.DISTRIBUTION, (ReturnType.DISTRIBUTION,)
        ),
        _operator(
            "frame_entropy", OperatorKind.DISTRIBUTION, (ReturnType.DISTRIBUTION,)
        ),
    )


def _set_specs() -> tuple[OperatorSpec, ...]:
    return (
        _operator("jaccard", OperatorKind.SET, (ReturnType.SET, ReturnType.SET)),
        _operator("coverage_ratio", OperatorKind.SET, (ReturnType.SET, ReturnType.SET)),
        _operator("set_count", OperatorKind.SET, (ReturnType.SET,)),
    )


def _graph_specs() -> tuple[OperatorSpec, ...]:
    names = (
        "graph_degree",
        "graph_pagerank",
        "graph_betweenness",
        "graph_neighbor_mean",
        "graph_neighbor_sum",
        "graph_path_count",
        "graph_bridge_score",
        "graph_community_count",
    )
    return tuple(
        _operator(name, OperatorKind.GRAPH, (ReturnType.GRAPH_NODE,)) for name in names
    )


def _future_operator_specs() -> tuple[OperatorSpec, ...]:
    names = ("future_event_growth", "future_provider_spread", "future_claim_conflict")
    return tuple(
        OperatorSpec(
            name, OperatorKind.ELEMENT, _one_numeric(), ReturnType.NUMERIC, True
        )
        for name in names
    )


def _operator(
    name: str,
    kind: OperatorKind,
    argument_types: tuple[ReturnType, ...],
) -> OperatorSpec:
    return OperatorSpec(name, kind, argument_types, ReturnType.NUMERIC)


def _one_numeric() -> tuple[ReturnType, ...]:
    return (ReturnType.NUMERIC,)


def _two_numeric() -> tuple[ReturnType, ...]:
    return (ReturnType.NUMERIC, ReturnType.NUMERIC)


def _two_distributions() -> tuple[ReturnType, ...]:
    return (ReturnType.DISTRIBUTION, ReturnType.DISTRIBUTION)
