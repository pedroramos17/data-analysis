"""Typed symbolic formula enums."""

from __future__ import annotations

from enum import Enum


class ReturnType(Enum):
    """Supported symbolic return types.

    Example:
        `ReturnType.NUMERIC`
    """

    UNKNOWN = "unknown"
    NUMERIC = "numeric"
    BOOLEAN = "boolean"
    CATEGORY = "category"
    DISTRIBUTION = "distribution"
    SET = "set"
    GRAPH_NODE = "graph_node"
    GRAPH_EDGE = "graph_edge"
    SCALAR = "scalar"
    FACTOR = "factor"


class ObjectLevel(Enum):
    """Sourceflow object levels for symbolic operands.

    Example:
        `ObjectLevel.EVENT`
    """

    ARTICLE = "article"
    SOURCE = "source"
    PROVIDER = "provider"
    OWNER = "owner"
    EVENT = "event"
    CLAIM = "claim"
    ENTITY = "entity"
    FRAME = "frame"
    EVIDENCE_SPAN = "evidence_span"


class OperatorKind(Enum):
    """Operator families used by validation and search.

    Example:
        `OperatorKind.TIME_SERIES`
    """

    ELEMENT = "element"
    TIME_SERIES = "time_series"
    GROUP = "group"
    DISTRIBUTION = "distribution"
    SET = "set"
    GRAPH = "graph"
    POST_PROCESS = "post_process"
