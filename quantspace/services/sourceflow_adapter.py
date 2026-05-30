"""Adapter from QuantSpace candidates to Sourceflow formula JSON."""

from __future__ import annotations

from typing import Protocol


class SourceflowAdapterCandidate(Protocol):
    """Minimal candidate shape needed by the Sourceflow adapter.

    Example:
        `adapt_factor_candidate_to_sourceflow_formula(candidate)`
    """

    pk: int | None
    name: str
    status: str
    paper_id: int | None
    support_status: str
    expression_json: dict[str, object]
    metadata_json: dict[str, object] | None


SUPPORTED_OPERATORS = frozenset(
    {
        "rank",
        "zscore",
        "delay",
        "delta",
        "mean",
        "std",
        "corr",
        "ts_rank",
        "winsorize",
        "neutralize",
        "div_safe",
        "log1p_abs",
    }
)
PASS_THROUGH_FIELDS = frozenset(
    {
        "window",
        "period",
        "lag",
        "group",
        "limit",
        "threshold",
        "return_type",
        "metadata",
    }
)


def can_adapt_factor_candidate(candidate: SourceflowAdapterCandidate) -> bool:
    """Return whether a QuantSpace factor can cross the Sourceflow boundary.

    Example:
        `can_adapt_factor_candidate(candidate)`
    """
    return not explain_adapter_limitations(candidate)


def adapt_factor_candidate_to_sourceflow_formula(
    candidate: SourceflowAdapterCandidate,
) -> dict[str, object]:
    """Return Sourceflow-compatible formula JSON without persisting it.

    Example:
        `adapt_factor_candidate_to_sourceflow_formula(candidate)["expression_json"]`
    """
    limitations = explain_adapter_limitations(candidate)
    if limitations:
        raise ValueError(_limitation_error(candidate, limitations))
    return {
        "name": candidate.name,
        "source": "quantspace",
        "status": candidate.status,
        "expression_json": _adapt_expression(candidate.expression_json),
        "metadata": _adapter_metadata(candidate, limitations),
    }


def explain_adapter_limitations(candidate: SourceflowAdapterCandidate) -> list[str]:
    """Explain why a candidate cannot be adapted safely.

    Example:
        `explain_adapter_limitations(candidate)`
    """
    expression = candidate.expression_json
    if not isinstance(expression, dict) or not expression:
        return ["Missing expression_json dict; expected Sourceflow formula JSON"]
    return _expression_limitations(expression, path="expression_json")


def _adapt_expression(node: dict[str, object]) -> dict[str, object]:
    kind = str(node.get("kind") or _default_kind(node))
    if kind == "operand":
        return _adapt_operand(node)
    if kind == "constant":
        return _adapt_constant(node)
    return _adapt_operator_node(node, kind)


def _adapt_operand(node: dict[str, object]) -> dict[str, object]:
    adapted = {"kind": "operand", "name": str(node["name"])}
    adapted["return_type"] = str(node.get("return_type") or "numeric")
    return adapted


def _adapt_constant(node: dict[str, object]) -> dict[str, object]:
    adapted = {"kind": "constant", "value": node["value"]}
    adapted["return_type"] = str(node.get("return_type") or "numeric")
    return adapted


def _adapt_operator_node(node: dict[str, object], kind: str) -> dict[str, object]:
    adapted = {"kind": kind, "name": _operator_name(node)}
    _copy_passthrough_fields(node, adapted)
    _adapt_known_children(node, adapted)
    return adapted


def _copy_passthrough_fields(
    source: dict[str, object],
    target: dict[str, object],
) -> None:
    for field in PASS_THROUGH_FIELDS:
        if field in source:
            target[field] = source[field]


def _adapt_known_children(
    source: dict[str, object],
    target: dict[str, object],
) -> None:
    for field in ("input", "left", "right"):
        child = source.get(field)
        if isinstance(child, dict):
            target[field] = _adapt_expression(child)
    args = source.get("args")
    if isinstance(args, list):
        target["args"] = [
            _adapt_expression(arg) for arg in args if isinstance(arg, dict)
        ]


def _expression_limitations(node: dict[str, object], path: str) -> list[str]:
    kind = str(node.get("kind") or _default_kind(node))
    if kind == "operand":
        return _operand_limitations(node, path)
    if kind == "constant":
        return _constant_limitations(node, path)
    return _operator_limitations(node, path)


def _operand_limitations(node: dict[str, object], path: str) -> list[str]:
    if str(node.get("name") or "").strip():
        return []
    return [f"{path} operand is missing name; expected non-empty string"]


def _constant_limitations(node: dict[str, object], path: str) -> list[str]:
    if "value" in node:
        return []
    return [f"{path} constant is missing value; expected scalar value"]


def _operator_limitations(node: dict[str, object], path: str) -> list[str]:
    kind = str(node.get("kind") or _default_kind(node))
    operator = _operator_name(node)
    limitations = _operator_name_limitations(operator, path)
    limitations.extend(_required_child_limitations(node, kind, path))
    limitations.extend(_child_limitations(node, path))
    return limitations


def _required_child_limitations(
    node: dict[str, object],
    kind: str,
    path: str,
) -> list[str]:
    if kind == "unary":
        return _missing_field_limitations(node, path, ("input",))
    if kind == "binary":
        return _missing_field_limitations(node, path, ("left", "right"))
    if kind == "function":
        return _function_args_limitations(node.get("args"), f"{path}.args")
    return []


def _missing_field_limitations(
    node: dict[str, object],
    path: str,
    fields: tuple[str, ...],
) -> list[str]:
    return [
        f"{path}.{field} is missing; expected dict formula node"
        for field in fields
        if node.get(field) is None
    ]


def _function_args_limitations(args: object, path: str) -> list[str]:
    if args is None:
        return [f"{path} is missing; expected non-empty list of formula nodes"]
    if isinstance(args, list) and not args:
        return [f"{path} is empty; expected non-empty list of formula nodes"]
    return []


def _operator_name_limitations(operator: str, path: str) -> list[str]:
    if not operator:
        return [f"{path} is missing operator/name; expected supported operator"]
    if operator in SUPPORTED_OPERATORS:
        return []
    expected = ", ".join(sorted(SUPPORTED_OPERATORS))
    return [f"Unsupported operator '{operator}' at {path}; expected one of {expected}"]


def _child_limitations(node: dict[str, object], path: str) -> list[str]:
    limitations: list[str] = []
    for field in ("input", "left", "right"):
        child = node.get(field)
        limitations.extend(_one_child_limitations(child, f"{path}.{field}"))
    limitations.extend(_args_limitations(node.get("args"), f"{path}.args"))
    return limitations


def _one_child_limitations(child: object, path: str) -> list[str]:
    if child is None:
        return []
    if isinstance(child, dict):
        return _expression_limitations(child, path)
    return [f"{path} has invalid child {child!r}; expected dict formula node"]


def _args_limitations(args: object, path: str) -> list[str]:
    if args is None:
        return []
    if not isinstance(args, list):
        return [f"{path} has invalid args {args!r}; expected list of formula nodes"]
    return _list_child_limitations(args, path)


def _list_child_limitations(args: list[object], path: str) -> list[str]:
    limitations: list[str] = []
    for index, child in enumerate(args):
        limitations.extend(_one_child_limitations(child, f"{path}[{index}]"))
    return limitations


def _operator_name(node: dict[str, object]) -> str:
    return str(node.get("name") or node.get("operator") or "").strip()


def _default_kind(node: dict[str, object]) -> str:
    if "value" in node:
        return "constant"
    if "operator" in node:
        return "function"
    if "args" in node:
        return "function"
    if "input" in node:
        return "unary"
    if "left" in node or "right" in node:
        return "binary"
    return "operand"


def _adapter_metadata(
    candidate: SourceflowAdapterCandidate,
    limitations: list[str],
) -> dict[str, object]:
    metadata_value = candidate.metadata_json or {}
    metadata = metadata_value if isinstance(metadata_value, dict) else {}
    return {
        "adapter": "quantspace.sourceflow_formula_json",
        "adapter_boundary": "non_persistent",
        "paper_id": candidate.paper_id,
        "quantspace_factor_candidate_id": candidate.pk,
        "support_status": candidate.support_status,
        "validation_status": candidate.status,
        "claims_validity": False,
        "evidence_chunk_ids": list(metadata.get("evidence_chunk_ids", [])),
        "limitations": limitations,
    }


def _limitation_error(
    candidate: SourceflowAdapterCandidate,
    limitations: list[str],
) -> str:
    joined = "; ".join(limitations)
    return (
        f"Cannot adapt FactorCandidate {candidate.pk}; "
        f"expected compatible formula: {joined}"
    )
