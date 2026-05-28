"""Compile symbolic formulas into dataframe execution plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from sourceflow.intelligence.factor_base.dependencies import expression_dependencies
from sourceflow.intelligence.factor_base.storage import FactorValueStorage
from sourceflow.intelligence.factor_base.types import (
    FactorDefinition,
    FactorExecutionPlan,
)
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
)
from sourceflow.intelligence.symbolic.operators import operator_functions
from sourceflow.intelligence.symbolic.validator import validate_formula

GROUP_OPERATORS = (
    "group_mean",
    "group_sum",
    "group_std",
    "group_rank",
    "group_share",
    "group_entropy",
    "group_topk_share",
    "group_median",
)
EVENT_STANDARDIZERS = ("zscore_by_event", "standardize_by_event")


@dataclass(frozen=True, slots=True)
class FactorExecutionContext:
    """Execution data available to compiled symbolic formulas.

    Example:
        `context = FactorExecutionContext.from_frame(frame, Path("exports"))`
    """

    as_of: datetime
    history_start: datetime
    history_end: datetime
    operand_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    factor_storage: FactorValueStorage | None = None
    output_dir: Path = Path("exports")
    connection: object | None = None

    @classmethod
    def from_frame(
        cls,
        frame: pd.DataFrame,
        output_dir: Path,
    ) -> FactorExecutionContext:
        """Build a local execution context from a dataframe.

        Example:
            `context = FactorExecutionContext.from_frame(frame, Path("exports"))`
        """
        now = _frame_now(frame)
        return cls(
            now, now, now, frame, FactorValueStorage(output_dir / "factors"), output_dir
        )

    def factor_series(self, factor_name: str, frame: pd.DataFrame) -> pd.Series:
        """Load a factor value series aligned to frame entity ids.

        Example:
            `series = context.factor_series("coverage_intensity", frame)`
        """
        if self.factor_storage is None:
            return pd.Series(0.0, index=frame.index)
        path = self.factor_storage.latest_path(factor_name)
        if path is None:
            return pd.Series(0.0, index=frame.index)
        values = self.factor_storage.read_values(path)
        values = _available_factor_rows(values, self.as_of)
        return _aligned_factor_series(frame, values)


def compile_formula(
    factor_name: str | FactorDefinition,
    expression: FormulaExpression | None = None,
    constraints: SearchConstraints | None = None,
    context: FactorExecutionContext | None = None,
) -> FactorExecutionPlan:
    """Compile a formula into a dataframe execution plan.

    Example:
        `plan = compile_formula("coverage", operand("article_count"))`
    """
    name, active_expression = _definition_parts(factor_name, expression)
    active_constraints = constraints or SearchConstraints()
    validation = validate_formula(active_expression, active_constraints)
    if not validation.is_valid:
        raise ValueError(
            f"Invalid formula {name}; expected valid formula: {validation.errors}"
        )
    dependencies = expression_dependencies(active_expression)
    active_context = context or FactorExecutionContext.from_frame(
        pd.DataFrame(), Path("exports")
    )
    compiled = _compile_node(active_expression, active_context)
    return FactorExecutionPlan(
        name,
        dependencies,
        _availability_executor(compiled, active_context),
    )


def execute_factor(
    definition: FactorDefinition,
    context: FactorExecutionContext,
) -> list[dict[str, object]]:
    """Execute one factor and return Parquet-ready rows.

    Example:
        `rows = execute_factor(definition, context)`
    """
    plan = compile_formula(definition, context=context)
    values = plan.execute(context.operand_frame)
    return _factor_rows(definition.name, context.operand_frame, values)


def _compile_node(
    expression: FormulaExpression,
    context: FactorExecutionContext,
) -> object:
    if isinstance(expression, SymbolicOperand):
        return _compile_operand(expression, context)
    if isinstance(expression, SymbolicConstant):
        return lambda frame: pd.Series(expression.value, index=frame.index)
    if isinstance(expression, UnaryExpression):
        return _compile_unary(expression.name, expression.child, context)
    if isinstance(expression, PostProcessExpression):
        return _compile_unary(expression.name, expression.child, context)
    if isinstance(expression, TimeSeriesExpression):
        return _compile_time_series(expression, context)
    if isinstance(expression, GroupExpression):
        return _compile_group(expression, context)
    if isinstance(expression, BinaryExpression | DistributionExpression):
        return _compile_binary(
            expression.name, expression.left, expression.right, context
        )
    if isinstance(expression, GraphExpression | FunctionCall):
        return _compile_graph_or_call(expression, context)
    raise ValueError(f"Invalid expression {expression}; expected formula node")


def _availability_executor(
    compiled: object,
    context: FactorExecutionContext,
) -> object:
    def execute_available(frame: pd.DataFrame) -> pd.Series:
        return compiled(_available_frame(frame, context.as_of))

    return execute_available


def _compile_operand(
    expression: SymbolicOperand,
    context: FactorExecutionContext,
) -> object:
    if expression.return_type.value == "factor":
        return lambda frame: context.factor_series(expression.name, frame)
    return lambda frame: frame.get(expression.name, pd.Series(0.0, index=frame.index))


def _compile_unary(
    name: str,
    child: FormulaExpression,
    context: FactorExecutionContext,
) -> object:
    functions = operator_functions()
    compiled_child = _compile_node(child, context)
    if name in GROUP_OPERATORS:
        return _group_unary_executor(name, compiled_child, "event_id")
    if name in EVENT_STANDARDIZERS:
        return _group_zscore_executor(compiled_child, "event_id")
    if name == "standardize_by_source":
        return _group_zscore_executor(compiled_child, "source_id")
    if name == "neutralize_by_provider":
        return _neutralized_executor(compiled_child, "provider")
    if name == "neutralize_by_language":
        return _neutralized_executor(compiled_child, "language")
    return lambda frame: functions.get(name, _identity)(compiled_child(frame))


def _compile_binary(
    name: str,
    left: FormulaExpression,
    right: FormulaExpression,
    context: FactorExecutionContext,
) -> object:
    functions = operator_functions()
    compiled_left = _compile_node(left, context)
    compiled_right = _compile_node(right, context)
    return lambda frame: functions.get(name, _identity_binary)(
        compiled_left(frame), compiled_right(frame)
    )


def _group_unary_executor(
    name: str,
    compiled_child: object,
    group_key: str,
) -> object:
    def execute_group(frame: pd.DataFrame) -> pd.Series:
        return _group_values(name, compiled_child(frame), frame, group_key)

    return execute_group


def _group_zscore_executor(
    compiled_child: object,
    group_key: str,
) -> object:
    def execute_group_zscore(frame: pd.DataFrame) -> pd.Series:
        return _group_zscore(compiled_child(frame), frame, group_key)

    return execute_group_zscore


def _neutralized_executor(
    compiled_child: object,
    group_key: str,
) -> object:
    def execute_neutralized(frame: pd.DataFrame) -> pd.Series:
        return _neutralized_values(compiled_child(frame), frame, group_key)

    return execute_neutralized


def _compile_time_series(
    expression: TimeSeriesExpression,
    context: FactorExecutionContext,
) -> object:
    compiled_child = _compile_node(expression.child, context)
    return lambda frame: _time_series_values(
        expression.name,
        compiled_child(frame),
        frame,
    )


def _compile_group(
    expression: GroupExpression,
    context: FactorExecutionContext,
) -> object:
    compiled_child = _compile_node(expression.child, context)
    return lambda frame: _group_values(
        expression.name, compiled_child(frame), frame, expression.group_key
    )


def _compile_graph_or_call(
    expression: GraphExpression | FunctionCall,
    context: FactorExecutionContext,
) -> object:
    functions = operator_functions()
    compiled_args = tuple(_compile_node(arg, context) for arg in expression.args)
    return lambda frame: functions.get(expression.name, _first_arg)(
        *(arg(frame) for arg in compiled_args)
    )


def _group_values(
    name: str,
    values: pd.Series,
    frame: pd.DataFrame,
    group_key: str,
) -> pd.Series:
    if group_key not in frame:
        return values
    grouped = values.groupby(frame[group_key])
    if name == "group_sum":
        return grouped.transform("sum")
    if name == "group_median":
        return grouped.transform("median")
    if name in {"group_std", "group_entropy"}:
        return grouped.transform("std").fillna(0)
    if name == "group_rank":
        return grouped.rank(pct=True).fillna(0)
    if name == "group_share":
        return values / grouped.transform("sum").replace(0, 1)
    if name == "group_topk_share":
        return grouped.transform("max") / grouped.transform("sum").replace(0, 1)
    return grouped.transform("mean")


def _group_zscore(
    values: pd.Series,
    frame: pd.DataFrame,
    group_key: str,
) -> pd.Series:
    if group_key not in frame:
        return operator_functions()["zscore"](values)
    return values.groupby(frame[group_key]).transform(operator_functions()["zscore"])


def _neutralized_values(
    values: pd.Series,
    frame: pd.DataFrame,
    group_key: str,
) -> pd.Series:
    if group_key not in frame:
        return values
    grouped = values.groupby(frame[group_key])
    return values - grouped.transform("mean")


def _time_series_values(
    name: str,
    values: pd.Series,
    frame: pd.DataFrame,
) -> pd.Series:
    values = _time_ordered_values(values, frame)
    if name in {"ts_delta", "rolling_delta"}:
        return values.fillna(0).diff().fillna(0).reindex(frame.index).fillna(0)
    if name == "ts_std":
        return values.expanding().std().fillna(0).reindex(frame.index).fillna(0)
    if name in {"ts_rank", "ts_zscore"}:
        return values.rank(pct=True).fillna(0).reindex(frame.index).fillna(0)
    if name == "ts_sum":
        return values.expanding().sum().fillna(0).reindex(frame.index).fillna(0)
    return values.expanding().mean().fillna(0).reindex(frame.index).fillna(0)


def _definition_parts(
    factor_name: str | FactorDefinition,
    expression: FormulaExpression | None,
) -> tuple[str, FormulaExpression]:
    if isinstance(factor_name, FactorDefinition):
        return factor_name.name, factor_name.expression
    if expression is None:
        raise ValueError(
            f"Invalid expression {expression}; expected formula expression"
        )
    return factor_name, expression


def _aligned_factor_series(
    frame: pd.DataFrame,
    rows: list[dict[str, object]],
) -> pd.Series:
    by_entity = {
        str(row.get("entity_id", "")): float(row.get("value", 0) or 0) for row in rows
    }
    if "entity_id" not in frame:
        return pd.Series(0.0, index=frame.index)
    return (
        frame["entity_id"].map(lambda value: by_entity.get(str(value), 0.0)).fillna(0)
    )


def _factor_rows(
    factor_name: str,
    frame: pd.DataFrame,
    values: pd.Series,
) -> list[dict[str, object]]:
    rows = []
    for index, value in values.items():
        rows.append(_factor_row(factor_name, frame.loc[index], _safe_float(value)))
    return rows


def _factor_row(
    factor_name: str,
    source_row: pd.Series,
    value: float,
) -> dict[str, object]:
    return {
        "factor_name": factor_name,
        "entity_id": source_row.get("entity_id", ""),
        "event_id": source_row.get("event_id"),
        "source_id": source_row.get("source_id"),
        "as_of": source_row.get("as_of", ""),
        "value": value,
    }


def _frame_now(frame: pd.DataFrame) -> datetime:
    if "as_of" in frame and len(frame["as_of"]):
        return pd.to_datetime(frame["as_of"].iloc[-1]).to_pydatetime()
    return datetime.utcnow()


def _available_frame(frame: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    if "available_at" not in frame:
        return frame
    available_at = pd.to_datetime(frame["available_at"], errors="coerce", utc=True)
    as_of_value = pd.to_datetime(as_of, utc=True)
    mask = available_at.isna() | (available_at <= as_of_value)
    return frame.loc[mask]


def _available_factor_rows(
    rows: list[dict[str, object]],
    as_of: datetime,
) -> list[dict[str, object]]:
    return [row for row in rows if _row_available(row, as_of)]


def _row_available(row: dict[str, object], as_of: datetime) -> bool:
    raw_value = row.get("as_of") or row.get("available_at")
    if not raw_value:
        return True
    parsed = pd.to_datetime(raw_value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return True
    return parsed <= pd.to_datetime(as_of, utc=True)


def _time_ordered_values(values: pd.Series, frame: pd.DataFrame) -> pd.Series:
    if "as_of" not in frame:
        return values
    ordered_index = pd.to_datetime(frame["as_of"], errors="coerce").sort_values().index
    return values.reindex(ordered_index)


def _safe_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, list | tuple | set | dict):
        return 0.0
    if pd.isna(value):
        return 0.0
    return float(value)


def _identity(value: pd.Series) -> pd.Series:
    return value


def _identity_binary(left: pd.Series, _right: pd.Series) -> pd.Series:
    return left


def _first_arg(*args: pd.Series) -> pd.Series:
    return args[0] if args else pd.Series(dtype=float)
