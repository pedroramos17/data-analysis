"""Formula JSON serialization and human-readable rendering."""

from __future__ import annotations

from collections.abc import Mapping

from sourceflow.intelligence.symbolic.expression import (
    BinaryExpression,
    DistributionExpression,
    FormulaExpression,
    FunctionCall,
    GraphExpression,
    GroupExpression,
    PostProcessExpression,
    SymbolicConstant,
    SymbolicOperand,
    TimeSeriesExpression,
    UnaryExpression,
    binary,
    const,
    distribution_op,
    group_op,
    mapping_arg,
    operand,
    post_process,
    time_series,
    unary,
)
from sourceflow.intelligence.symbolic.types import ObjectLevel, ReturnType


def serialize_formula(expression: FormulaExpression) -> dict[str, object]:
    """Serialize a formula expression to JSON-compatible data.

    Example:
        `payload = serialize_formula(unary("log1p", operand("article_count")))`
    """
    if isinstance(expression, SymbolicOperand):
        return _operand_payload(expression)
    if isinstance(expression, SymbolicConstant):
        return _constant_payload(expression)
    if isinstance(expression, UnaryExpression):
        return _unary_payload(expression)
    if isinstance(expression, BinaryExpression):
        return _binary_payload(expression)
    if isinstance(expression, TimeSeriesExpression):
        return _time_series_payload(expression)
    if isinstance(expression, GroupExpression):
        return _group_payload(expression)
    if isinstance(expression, DistributionExpression):
        return _distribution_payload(expression)
    if isinstance(expression, GraphExpression | FunctionCall):
        return _graph_payload(expression)
    if isinstance(expression, PostProcessExpression):
        return _post_process_payload(expression)
    raise ValueError(f"Invalid expression {expression}; expected expression node")


def deserialize_formula(payload: Mapping[str, object]) -> FormulaExpression:
    """Deserialize a JSON-compatible formula payload.

    Example:
        `expression = deserialize_formula(payload)`
    """
    kind = str(payload.get("kind", ""))
    if kind == "operand":
        return _operand_from_payload(payload)
    if kind == "constant":
        return const(payload.get("value", 0.0))
    if kind == "unary":
        return unary(str(payload["name"]), _child(payload))
    if kind == "binary":
        return binary(str(payload["name"]), _left(payload), _right(payload))
    if kind == "time_series":
        return time_series(
            str(payload["name"]), _child(payload), str(payload["window"])
        )
    if kind == "group":
        return group_op(
            str(payload["name"]), _child(payload), str(payload["group_key"])
        )
    if kind == "distribution":
        return distribution_op(str(payload["name"]), _left(payload), _right(payload))
    if kind in {"graph", "call"}:
        return _graph_from_payload(payload, kind)
    if kind == "post_process":
        return post_process(str(payload["name"]), _child(payload))
    raise ValueError(f"Invalid expression kind {kind}; expected known formula node")


def formula_text(expression: FormulaExpression) -> str:
    """Render an expression to readable formula text.

    Example:
        `formula_text(unary("log1p", operand("article_count")))`
    """
    if isinstance(expression, SymbolicOperand):
        return expression.name
    if isinstance(expression, SymbolicConstant):
        return str(expression.value)
    if isinstance(expression, UnaryExpression):
        return f"{expression.name}({formula_text(expression.child)})"
    if isinstance(expression, BinaryExpression | DistributionExpression):
        return _binary_text(expression.name, expression.left, expression.right)
    if isinstance(expression, TimeSeriesExpression):
        return (
            f"{expression.name}({formula_text(expression.child)}, {expression.window})"
        )
    if isinstance(expression, GroupExpression):
        child_text = formula_text(expression.child)
        return f"{expression.name}({child_text}, {expression.group_key})"
    if isinstance(expression, GraphExpression | FunctionCall):
        args = ", ".join(formula_text(arg) for arg in expression.args)
        return f"{expression.name}({args})"
    if isinstance(expression, PostProcessExpression):
        return f"{expression.name}({formula_text(expression.child)})"
    raise ValueError(f"Invalid expression {expression}; expected expression node")


def _operand_payload(expression: SymbolicOperand) -> dict[str, object]:
    return {
        "kind": "operand",
        "name": expression.name,
        "return_type": expression.return_type.value,
        "operand_type": expression.return_type.value,
        "object_level": expression.object_level.value,
        "metadata": dict(expression.metadata),
        "window_hours": expression.window_hours,
    }


def _constant_payload(expression: SymbolicConstant) -> dict[str, object]:
    return {
        "kind": "constant",
        "value": expression.value,
        "return_type": expression.return_type.value,
        "value_type": expression.return_type.value,
    }


def _unary_payload(expression: UnaryExpression) -> dict[str, object]:
    return {
        "kind": expression.kind,
        "name": expression.name,
        "child": serialize_formula(expression.child),
    }


def _binary_payload(expression: BinaryExpression) -> dict[str, object]:
    return {
        "kind": expression.kind,
        "name": expression.name,
        "left": serialize_formula(expression.left),
        "right": serialize_formula(expression.right),
    }


def _time_series_payload(expression: TimeSeriesExpression) -> dict[str, object]:
    payload = _unary_payload(expression)
    payload["window"] = expression.window
    return payload


def _group_payload(expression: GroupExpression) -> dict[str, object]:
    payload = _unary_payload(expression)
    payload["group_key"] = expression.group_key
    return payload


def _distribution_payload(expression: DistributionExpression) -> dict[str, object]:
    return {
        "kind": expression.kind,
        "name": expression.name,
        "left": serialize_formula(expression.left),
        "right": serialize_formula(expression.right),
    }


def _graph_payload(expression: GraphExpression | FunctionCall) -> dict[str, object]:
    return {
        "kind": expression.kind,
        "name": expression.name,
        "args": [serialize_formula(arg) for arg in expression.args],
    }


def _post_process_payload(expression: PostProcessExpression) -> dict[str, object]:
    return {
        "kind": expression.kind,
        "name": expression.name,
        "child": serialize_formula(expression.child),
    }


def _operand_from_payload(payload: Mapping[str, object]) -> SymbolicOperand:
    raw_type = str(payload.get("return_type", payload.get("operand_type", "unknown")))
    raw_level = str(payload.get("object_level", ObjectLevel.EVENT.value))
    return operand(
        str(payload["name"]),
        ReturnType(raw_type),
        ObjectLevel(raw_level),
        _metadata(payload),
        int(payload.get("window_hours", 0)),
    )


def _metadata(payload: Mapping[str, object]) -> dict[str, object]:
    raw_metadata = payload.get("metadata", {})
    return dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}


def _child(payload: Mapping[str, object]) -> FormulaExpression:
    return deserialize_formula(mapping_arg(payload["child"]))


def _left(payload: Mapping[str, object]) -> FormulaExpression:
    return deserialize_formula(mapping_arg(payload["left"]))


def _right(payload: Mapping[str, object]) -> FormulaExpression:
    return deserialize_formula(mapping_arg(payload["right"]))


def _graph_from_payload(payload: Mapping[str, object], kind: str) -> FormulaExpression:
    raw_args = payload.get("args", ())
    if not isinstance(raw_args, list | tuple):
        raise ValueError(f"Invalid graph args {raw_args}; expected a sequence")
    args = tuple(deserialize_formula(mapping_arg(arg)) for arg in raw_args)
    return GraphExpression(kind, str(payload["name"]), args)


def _binary_text(
    name: str,
    left: FormulaExpression,
    right: FormulaExpression,
) -> str:
    return f"{name}({formula_text(left)}, {formula_text(right)})"
