"""Serializable typed expression tree classes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from sourceflow.intelligence.symbolic.types import ObjectLevel, ReturnType


@dataclass(frozen=True, slots=True)
class FormulaExpression:
    """Base expression node with a stable kind label.

    Example:
        `FormulaExpression(kind="constant")`
    """

    kind: str


@dataclass(frozen=True, slots=True)
class SymbolicOperand(FormulaExpression):
    """Reference a typed raw operand or another factor.

    Example:
        `SymbolicOperand("operand", "article_count", ReturnType.NUMERIC)`
    """

    name: str
    return_type: ReturnType = ReturnType.UNKNOWN
    object_level: ObjectLevel = ObjectLevel.EVENT
    metadata: MappingProxy = field(default_factory=dict)
    window_hours: int = 0

    @property
    def operand_type(self) -> ReturnType:
        """Return the legacy operand type alias.

        Example:
            `operand("article_count").operand_type`
        """
        return self.return_type


@dataclass(frozen=True, slots=True)
class SymbolicConstant(FormulaExpression):
    """Literal scalar value used inside a formula.

    Example:
        `SymbolicConstant("constant", 1.0)`
    """

    value: float | str | bool
    return_type: ReturnType = ReturnType.SCALAR

    @property
    def value_type(self) -> ReturnType:
        """Return the legacy constant type alias.

        Example:
            `const(1).value_type`
        """
        return self.return_type


@dataclass(frozen=True, slots=True)
class UnaryExpression(FormulaExpression):
    """Unary symbolic operator call.

    Example:
        `unary("log1p", operand("article_count"))`
    """

    name: str
    child: FormulaExpression


@dataclass(frozen=True, slots=True)
class BinaryExpression(FormulaExpression):
    """Binary symbolic operator call.

    Example:
        `binary("add", operand("a"), operand("b"))`
    """

    name: str
    left: FormulaExpression
    right: FormulaExpression


@dataclass(frozen=True, slots=True)
class TimeSeriesExpression(FormulaExpression):
    """Time-series symbolic operator call.

    Example:
        `time_series("ts_mean", operand("article_count"), "24h")`
    """

    name: str
    child: FormulaExpression
    window: str


@dataclass(frozen=True, slots=True)
class GroupExpression(FormulaExpression):
    """Group symbolic operator call.

    Example:
        `group_op("group_mean", operand("article_count"), "provider")`
    """

    name: str
    child: FormulaExpression
    group_key: str


@dataclass(frozen=True, slots=True)
class DistributionExpression(FormulaExpression):
    """Distribution comparison operator call.

    Example:
        `distribution_op("js_divergence", left, right)`
    """

    name: str
    left: FormulaExpression
    right: FormulaExpression


@dataclass(frozen=True, slots=True)
class GraphExpression(FormulaExpression):
    """Graph symbolic operator call.

    Example:
        `graph_op("graph_pagerank", operand("entity_node"))`
    """

    name: str
    args: tuple[FormulaExpression, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class PostProcessExpression(FormulaExpression):
    """Cross-sectional post-processing operator call.

    Example:
        `post_process("rank", operand("article_count"))`
    """

    name: str
    child: FormulaExpression


@dataclass(frozen=True, slots=True)
class FunctionCall(FormulaExpression):
    """Legacy generic function call used by seed definitions.

    Example:
        `FunctionCall("call", "log1p", (operand("article_count"),))`
    """

    name: str
    args: tuple[FormulaExpression, ...] = field(default_factory=tuple)


MappingProxy = dict[str, object]
OperandRef = SymbolicOperand
ConstantValue = SymbolicConstant


def operand(
    name: str,
    return_type: ReturnType = ReturnType.UNKNOWN,
    object_level: ObjectLevel = ObjectLevel.EVENT,
    metadata: MappingProxy | None = None,
    window_hours: int = 0,
) -> SymbolicOperand:
    """Build an operand reference.

    Example:
        `operand("article_count")`
    """
    return SymbolicOperand(
        "operand", name, return_type, object_level, metadata or {}, window_hours
    )


def factor(name: str, object_level: ObjectLevel = ObjectLevel.EVENT) -> SymbolicOperand:
    """Build a dependency reference to another factor.

    Example:
        `factor("event_conflict_risk")`
    """
    return operand(name, ReturnType.FACTOR, object_level)


def const(value: float | str | bool) -> SymbolicConstant:
    """Build a scalar constant.

    Example:
        `const(1.0)`
    """
    return_type = (
        ReturnType.NUMERIC if isinstance(value, int | float) else ReturnType.SCALAR
    )
    return SymbolicConstant("constant", value, return_type)


def unary(name: str, child: FormulaExpression) -> UnaryExpression:
    """Build a unary expression.

    Example:
        `unary("log1p", operand("article_count"))`
    """
    return UnaryExpression("unary", name, child)


def binary(
    name: str, left: FormulaExpression, right: FormulaExpression
) -> BinaryExpression:
    """Build a binary expression.

    Example:
        `binary("add", operand("a"), operand("b"))`
    """
    return BinaryExpression("binary", name, left, right)


def time_series(
    name: str, child: FormulaExpression, window: str | int
) -> TimeSeriesExpression:
    """Build a time-series expression.

    Example:
        `time_series("ts_mean", operand("article_count"), "24h")`
    """
    return TimeSeriesExpression("time_series", name, child, str(window))


def group_op(name: str, child: FormulaExpression, group_key: str) -> GroupExpression:
    """Build a group expression.

    Example:
        `group_op("group_mean", operand("article_count"), "provider")`
    """
    return GroupExpression("group", name, child, group_key)


def distribution_op(
    name: str, left: FormulaExpression, right: FormulaExpression
) -> DistributionExpression:
    """Build a distribution expression.

    Example:
        `distribution_op("js_divergence", left, right)`
    """
    return DistributionExpression("distribution", name, left, right)


def graph_op(name: str, *args: FormulaExpression) -> GraphExpression:
    """Build a graph expression.

    Example:
        `graph_op("graph_pagerank", operand("entity_node"))`
    """
    return GraphExpression("graph", name, tuple(args))


def post_process(name: str, child: FormulaExpression) -> PostProcessExpression:
    """Build a post-processing expression.

    Example:
        `post_process("rank", operand("article_count"))`
    """
    return PostProcessExpression("post_process", name, child)


def call(name: str, *args: FormulaExpression) -> FormulaExpression:
    """Build a compatibility operator call.

    Example:
        `call("log1p", operand("article_count"))`
    """
    if len(args) == 1:
        return unary(name, args[0])
    if len(args) == 2:
        return binary(name, args[0], args[1])
    return FunctionCall("call", name, tuple(args))


def expression_to_dict(expression: FormulaExpression) -> dict[str, object]:
    """Serialize an expression tree to JSON-compatible data.

    Example:
        `payload = expression_to_dict(call("log1p", operand("article_count")))`
    """
    from sourceflow.intelligence.symbolic.serializer import serialize_formula

    return serialize_formula(expression)


def expression_from_dict(payload: Mapping[str, object]) -> FormulaExpression:
    """Deserialize an expression tree from JSON-compatible data.

    Example:
        `expr = expression_from_dict(payload)`
    """
    from sourceflow.intelligence.symbolic.serializer import deserialize_formula

    return deserialize_formula(payload)


def formula_text(expression: FormulaExpression) -> str:
    """Render an expression as display-only formula text.

    Example:
        `formula_text(call("log1p", operand("article_count")))`
    """
    from sourceflow.intelligence.symbolic.serializer import formula_text as render

    return render(expression)


def expression_depth(expression: FormulaExpression) -> int:
    """Return the maximum tree depth for complexity checks.

    Example:
        `expression_depth(call("log1p", operand("article_count")))`
    """
    children = expression_children(expression)
    if not children:
        return 1
    return 1 + max(expression_depth(child) for child in children)


def operator_count(expression: FormulaExpression) -> int:
    """Return the number of operator calls in a tree.

    Example:
        `operator_count(call("log1p", operand("article_count")))`
    """
    children = expression_children(expression)
    count = 0 if isinstance(expression, SymbolicOperand | SymbolicConstant) else 1
    return count + sum(operator_count(child) for child in children)


def walk_expression(expression: FormulaExpression) -> tuple[FormulaExpression, ...]:
    """Return all expression nodes in pre-order.

    Example:
        `nodes = walk_expression(call("log1p", operand("article_count")))`
    """
    nodes: list[FormulaExpression] = [expression]
    for child in expression_children(expression):
        nodes.extend(walk_expression(child))
    return tuple(nodes)


def expression_children(expression: FormulaExpression) -> tuple[FormulaExpression, ...]:
    """Return direct expression children.

    Example:
        `children = expression_children(unary("abs", operand("x")))`
    """
    if isinstance(expression, UnaryExpression | TimeSeriesExpression | GroupExpression):
        return (expression.child,)
    if isinstance(expression, BinaryExpression | DistributionExpression):
        return (expression.left, expression.right)
    if isinstance(expression, GraphExpression | FunctionCall):
        return expression.args
    if isinstance(expression, PostProcessExpression):
        return (expression.child,)
    return ()


def mapping_arg(value: object) -> Mapping[str, object]:
    """Return a mapping expression child or raise a typed error.

    Example:
        `payload = mapping_arg({"kind": "operand"})`
    """
    if not isinstance(value, Mapping):
        raise ValueError(f"Invalid expression child {value}; expected mapping")
    return value
