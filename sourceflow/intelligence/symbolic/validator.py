"""Type and leakage validation for symbolic formula trees."""

from __future__ import annotations

from dataclasses import dataclass

from sourceflow.intelligence.search.constraints import SearchConstraints
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
    expression_depth,
    operator_count,
)
from sourceflow.intelligence.symbolic.grammar import (
    OperatorSpec,
    operand_specs,
    resolve_operand_type,
    resolve_operator,
)
from sourceflow.intelligence.symbolic.types import ReturnType


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Formula validation outcome.

    Example:
        `ValidationResult(True, (), ReturnType.NUMERIC)`
    """

    is_valid: bool
    errors: tuple[str, ...]
    return_type: ReturnType


def validate_formula(
    expression: FormulaExpression,
    constraints: SearchConstraints,
) -> ValidationResult:
    """Validate a formula for type safety, complexity, and leakage.

    Example:
        `validate_formula(operand("article_count"), SearchConstraints())`
    """
    errors: list[str] = []
    _check_complexity(expression, constraints, errors)
    return_type = _infer_type(expression, errors)
    _check_leakage(expression, errors)
    return ValidationResult(not errors, tuple(errors), return_type)


def infer_expression_type(expression: FormulaExpression) -> ReturnType:
    """Infer an expression type or return unknown.

    Example:
        `infer_expression_type(operand("article_count"))`
    """
    result = validate_formula(expression, SearchConstraints())
    return result.return_type


def _check_complexity(
    expression: FormulaExpression,
    constraints: SearchConstraints,
    errors: list[str],
) -> None:
    depth = expression_depth(expression)
    operators = operator_count(expression)
    if depth > constraints.max_depth:
        errors.append(f"Invalid depth {depth}; expected <= {constraints.max_depth}")
    if operators > constraints.max_operators:
        message = f"Invalid operator count {operators}; expected <= "
        errors.append(f"{message}{constraints.max_operators}")


def _infer_type(expression: FormulaExpression, errors: list[str]) -> ReturnType:
    if isinstance(expression, SymbolicOperand):
        return _operand_type(expression, errors)
    if isinstance(expression, SymbolicConstant):
        return expression.return_type
    if isinstance(expression, UnaryExpression | TimeSeriesExpression):
        return _unary_type(
            expression.name, _infer_type(expression.child, errors), errors
        )
    if isinstance(expression, GroupExpression | PostProcessExpression):
        return _unary_type(
            expression.name, _infer_type(expression.child, errors), errors
        )
    if isinstance(expression, BinaryExpression | DistributionExpression):
        return _binary_type(expression.name, expression.left, expression.right, errors)
    if isinstance(expression, GraphExpression | FunctionCall):
        return _call_type(expression.name, expression.args, errors)
    errors.append(f"Invalid expression {expression}; expected typed node")
    return ReturnType.UNKNOWN


def _operand_type(expression: SymbolicOperand, errors: list[str]) -> ReturnType:
    if expression.return_type != ReturnType.UNKNOWN:
        return expression.return_type
    resolved = resolve_operand_type(expression.name)
    if resolved == ReturnType.UNKNOWN:
        errors.append(f"Invalid operand {expression.name}; expected registered operand")
    return resolved


def _unary_type(name: str, observed: ReturnType, errors: list[str]) -> ReturnType:
    try:
        spec = resolve_operator(name)
    except ValueError as error:
        errors.append(str(error))
        return ReturnType.UNKNOWN
    _validate_types(name, (observed,), spec, errors)
    return spec.return_type


def _binary_type(
    name: str,
    left: FormulaExpression,
    right: FormulaExpression,
    errors: list[str],
) -> ReturnType:
    observed = (_infer_type(left, errors), _infer_type(right, errors))
    try:
        spec = resolve_operator(name)
    except ValueError as error:
        errors.append(str(error))
        return ReturnType.UNKNOWN
    _validate_types(name, observed, spec, errors)
    return spec.return_type


def _call_type(
    name: str,
    args: tuple[FormulaExpression, ...],
    errors: list[str],
) -> ReturnType:
    try:
        spec = resolve_operator(name)
    except ValueError as error:
        errors.append(str(error))
        return ReturnType.UNKNOWN
    observed = tuple(_infer_type(arg, errors) for arg in args)
    _validate_types(name, observed, spec, errors)
    return spec.return_type


def _validate_types(
    name: str,
    observed: tuple[ReturnType, ...],
    spec: OperatorSpec,
    errors: list[str],
) -> None:
    if _types_match(observed, spec.argument_types):
        return
    errors.append(_type_error(name, observed, spec.argument_types))


def _types_match(
    observed: tuple[ReturnType, ...],
    expected: tuple[ReturnType, ...],
) -> bool:
    if len(observed) != len(expected):
        return False
    pairs = zip(observed, expected, strict=True)
    return all(_type_matches(left, right) for left, right in pairs)


def _type_matches(observed: ReturnType, expected: ReturnType) -> bool:
    if observed == expected:
        return True
    return observed == ReturnType.FACTOR and expected == ReturnType.NUMERIC


def _check_leakage(expression: FormulaExpression, errors: list[str]) -> None:
    if isinstance(expression, SymbolicOperand):
        _check_operand_leakage(expression, errors)
    if isinstance(expression, FunctionCall | GraphExpression):
        _check_operator_leakage(expression.name, expression.args, errors)
    if isinstance(expression, BinaryExpression | DistributionExpression):
        _check_binary_leakage(expression, errors)
    if isinstance(expression, UnaryExpression | TimeSeriesExpression):
        if isinstance(expression, TimeSeriesExpression):
            _check_time_window(expression.window, errors)
        _check_unary_leakage(expression.name, expression.child, errors)
    if isinstance(expression, GroupExpression | PostProcessExpression):
        _check_unary_leakage(expression.name, expression.child, errors)


def _check_binary_leakage(
    expression: BinaryExpression | DistributionExpression,
    errors: list[str],
) -> None:
    _check_named_operator_leakage(expression.name, errors)
    _check_leakage(expression.left, errors)
    _check_leakage(expression.right, errors)


def _check_unary_leakage(
    name: str,
    child: FormulaExpression,
    errors: list[str],
) -> None:
    _check_named_operator_leakage(name, errors)
    _check_leakage(child, errors)


def _check_operator_leakage(
    name: str,
    args: tuple[FormulaExpression, ...],
    errors: list[str],
) -> None:
    _check_named_operator_leakage(name, errors)
    for arg in args:
        _check_leakage(arg, errors)


def _check_named_operator_leakage(name: str, errors: list[str]) -> None:
    try:
        spec = resolve_operator(name)
    except ValueError:
        return
    if spec.future_only:
        errors.append(f"Leakage operator {name}; expected past-only formula")


def _check_operand_leakage(expression: SymbolicOperand, errors: list[str]) -> None:
    spec = operand_specs().get(expression.name)
    if spec and spec.future_only:
        errors.append(f"Leakage operand {expression.name}; expected past-only operand")
    if expression.window_hours < 0:
        errors.append(
            f"Invalid window {expression.window_hours}; expected non-negative hours"
        )


def _check_time_window(window: str, errors: list[str]) -> None:
    normalized = str(window).strip().lower()
    if not normalized:
        errors.append(f"Invalid window {window}; expected positive duration")
        return
    suffix = normalized[-1]
    amount = normalized[:-1] if suffix in {"h", "d"} else normalized
    if not amount.isdigit() or int(amount) <= 0:
        errors.append(f"Invalid window {window}; expected positive duration")


def _type_error(
    name: str,
    observed: tuple[ReturnType, ...],
    expected: tuple[ReturnType, ...],
) -> str:
    observed_names = ",".join(item.value for item in observed)
    expected_names = ",".join(item.value for item in expected)
    return f"Invalid types for {name}: {observed_names}; expected {expected_names}"
