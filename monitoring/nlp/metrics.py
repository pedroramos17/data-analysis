"""Persistence helpers for NLP pipeline cost metrics."""

from __future__ import annotations

from monitoring.models import NlpRunMetric


def save_nlp_run_metric(
    pipeline_result: dict[str, object],
    entrypoint: str,
) -> NlpRunMetric:
    """Persist a pipeline run metric without storing source text.

    Example:
        `metric = save_nlp_run_metric(result, "dashboard")`
    """
    text_block = _nested_dict(pipeline_result.get("text"))
    cost_block = _nested_dict(pipeline_result.get("cost"))
    metric = NlpRunMetric.objects.create(
        entrypoint=entrypoint,
        tasks=list(pipeline_result.get("tasks", [])),
        text_hash=str(text_block.get("hash", "")),
        text_length=int(text_block.get("length", 0)),
        token_count=int(text_block.get("tokens", 0)),
        total_ms=float(cost_block.get("total_ms", 0)),
        task_costs=_nested_dict(cost_block.get("tasks")),
        model_versions=_string_dict(pipeline_result.get("model_versions")),
        success=_success_from_costs(cost_block),
        error_message=_error_from_costs(cost_block),
    )
    return metric


def _nested_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _success_from_costs(cost_block: dict[str, object]) -> bool:
    task_costs = _nested_dict(cost_block.get("tasks"))
    statuses = [_nested_dict(cost).get("status", "") for cost in task_costs.values()]
    return all(status != "error" for status in statuses)


def _error_from_costs(cost_block: dict[str, object]) -> str:
    task_costs = _nested_dict(cost_block.get("tasks"))
    errors = [_nested_dict(cost).get("error", "") for cost in task_costs.values()]
    return "; ".join(str(error) for error in errors if error)
