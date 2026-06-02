"""Django views for the Sourceflow intelligence operator UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db import connection
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from monitoring.intelligence_actions import (
    compute_seed_factors_action,
    evaluate_factor_action,
    generate_formula_preview_action,
    register_seed_factors_action,
)
from sourceflow.intelligence.evaluation.objectives import objective_names
from sourceflow.intelligence.factor_base.registry import FactorRegistry
from sourceflow.intelligence.factor_base.storage import FactorValueStorage
from sourceflow.intelligence.factor_base.types import (
    FactorDefinition,
    FactorValueArtifact,
)
from sourceflow.intelligence.symbolic.expression import expression_to_dict, formula_text
from sourceflow.intelligence.xai.explain_factor import explain_factor


@dataclass(frozen=True, slots=True)
class IntelligenceFactorRow:
    """Display metadata for a registered factor.

    Example:
        `row = IntelligenceFactorRow("coverage", "desc", "formula", "event", (), "")`
    """

    name: str
    description: str
    formula: str
    entity_type: str
    dependencies: tuple[str, ...]
    explanation: str


class IntelligenceDashboardView(TemplateView):
    """Render the Sourceflow intelligence overview.

    Example:
        `GET /intelligence/`
    """

    template_name = "monitoring/intelligence_dashboard.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add registry summaries and run form choices.

        Example:
            Django calls this while rendering the dashboard.
        """
        context = super().get_context_data(**kwargs)
        registry = _registry()
        context.update(_dashboard_context(registry, self.request))
        return context


class IntelligenceFactorListView(TemplateView):
    """Render registered symbolic factors.

    Example:
        `GET /intelligence/factors/`
    """

    template_name = "monitoring/intelligence_factor_list.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add factor rows to the list page.

        Example:
            Django calls this while rendering the factor list.
        """
        context = super().get_context_data(**kwargs)
        registry = _registry()
        factors = registry.list_factors()
        context["factor_rows"] = _factor_rows(registry, factors)
        return context


class IntelligenceFactorDetailView(TemplateView):
    """Render one factor definition, artifacts, and explanation.

    Example:
        `GET /intelligence/factors/coverage_intensity/`
    """

    template_name = "monitoring/intelligence_factor_detail.html"

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        """Add formula, dependency, and latest artifact context.

        Example:
            Django calls this while rendering a factor detail.
        """
        context = super().get_context_data(**kwargs)
        registry = _registry()
        factor = _get_factor_or_404(registry, str(self.kwargs["name"]))
        context.update(_factor_detail_context(registry, factor))
        return context


def intelligence_factor_rows_api(request: HttpRequest, name: str) -> JsonResponse:
    """Return a bounded JSON preview of the latest factor values.

    Example:
        `GET /intelligence/factors/coverage_intensity/rows/?page_size=10`
    """
    registry = _registry()
    artifact = registry.latest_factor_value_artifact(name)
    if artifact is None:
        return JsonResponse(_empty_rows_payload("No factor value artifact found."))
    rows, error = _artifact_rows_or_error(artifact)
    if error:
        return JsonResponse(_empty_rows_payload(error))
    payload = _rows_payload(rows, request)
    return JsonResponse(payload)


@require_POST
def register_symbolic_factors_action(request: HttpRequest) -> HttpResponse:
    """Register seed factors from a guarded POST.

    Example:
        `POST /intelligence/actions/register/`
    """
    result = register_seed_factors_action(connection)
    messages.success(request, result.message)
    return redirect("monitoring:intelligence-dashboard")


@require_POST
def compute_symbolic_factors_action(request: HttpRequest) -> HttpResponse:
    """Compute seed factor values from a guarded POST.

    Example:
        `POST /intelligence/actions/compute/`
    """
    result = compute_seed_factors_action(
        connection,
        _export_dir(),
        request.POST.get("as_of", ""),
        request.POST.get("history_start", ""),
        request.POST.get("history_end", ""),
    )
    messages.success(request, result.message)
    return redirect("monitoring:intelligence-dashboard")


@require_POST
def search_symbolic_factors_action(request: HttpRequest) -> HttpResponse:
    """Generate a bounded preview of random valid formulas.

    Example:
        `POST /intelligence/actions/search/`
    """
    result = generate_formula_preview_action(
        _post_int(request, "count", 500, 5000),
        _post_int(request, "seed", 7, 1_000_000),
    )
    request.session["intelligence_formula_preview"] = list(result.preview)
    messages.success(request, result.message)
    return redirect("monitoring:intelligence-dashboard")


@require_POST
def evaluate_symbolic_factor_action(request: HttpRequest) -> HttpResponse:
    """Evaluate one persisted factor against a future-only objective.

    Example:
        `POST /intelligence/actions/evaluate/`
    """
    result = evaluate_factor_action(
        connection,
        _export_dir(),
        request.POST.get("factor", "coverage_intensity"),
        request.POST.get("objective", "future_event_growth"),
    )
    messages.success(request, result.message)
    return redirect("monitoring:intelligence-dashboard")


def _dashboard_context(
    registry: FactorRegistry,
    request: HttpRequest,
) -> dict[str, object]:
    factors = registry.list_factors()
    return {
        "summary": registry.summary(),
        "factors": factors,
        "objectives": objective_names(),
        "latest_artifacts": registry.list_factor_value_artifacts(limit=8),
        "recent_evaluations": registry.list_factor_evaluations(limit=8),
        "formula_preview": request.session.get("intelligence_formula_preview", ()),
    }


def _factor_detail_context(
    registry: FactorRegistry,
    factor: FactorDefinition,
) -> dict[str, object]:
    artifact = registry.latest_factor_value_artifact(factor.name)
    return {
        "factor": factor,
        "formula": formula_text(factor.expression),
        "formula_json": _formula_json(factor),
        "dependencies": registry.factor_dependencies(factor.name),
        "explanation": explain_factor(factor.name),
        "artifacts": registry.list_factor_value_artifacts(factor.name, limit=20),
        "latest_artifact": artifact,
        "preview": _artifact_preview(artifact),
    }


def _factor_rows(
    registry: FactorRegistry,
    factors: tuple[FactorDefinition, ...],
) -> tuple[IntelligenceFactorRow, ...]:
    return tuple(_factor_row(registry, factor) for factor in factors)


def _factor_row(
    registry: FactorRegistry,
    factor: FactorDefinition,
) -> IntelligenceFactorRow:
    return IntelligenceFactorRow(
        factor.name,
        factor.description,
        formula_text(factor.expression),
        factor.entity_type,
        registry.factor_dependencies(factor.name),
        explain_factor(factor.name),
    )


def _artifact_preview(artifact: FactorValueArtifact | None) -> dict[str, object]:
    if artifact is None:
        return _empty_rows_payload("No factor value artifact has been written yet.")
    rows, error = _artifact_rows_or_error(artifact)
    if error:
        return _empty_rows_payload(error)
    return _table_payload(rows, page=1, page_size=10, search="")


def _artifact_rows_or_error(
    artifact: FactorValueArtifact,
) -> tuple[list[dict[str, object]], str]:
    try:
        return _read_artifact_rows(artifact), ""
    except RuntimeError as error:
        return [], str(error)


def _read_artifact_rows(artifact: FactorValueArtifact) -> list[dict[str, object]]:
    storage = FactorValueStorage(_export_dir() / "factors")
    return storage.read_values(artifact.parquet_path)


def _rows_payload(
    rows: list[dict[str, object]],
    request: HttpRequest,
) -> dict[str, object]:
    return _table_payload(
        rows,
        page=_query_int(request, "page", 1),
        page_size=_query_int(request, "page_size", 25),
        search=request.GET.get("search", ""),
    )


def _table_payload(
    rows: list[dict[str, object]],
    page: int,
    page_size: int,
    search: str,
) -> dict[str, object]:
    bounded_size = max(1, min(page_size, 100))
    filtered = _filter_rows(rows, search)
    start = max(0, page - 1) * bounded_size
    visible_rows = filtered[start : start + bounded_size]
    return {
        "columns": _columns(rows),
        "rows": [_json_row(row) for row in visible_rows],
        "total": len(filtered),
    }


def _filter_rows(
    rows: list[dict[str, object]],
    search: str,
) -> list[dict[str, object]]:
    if not search:
        return rows
    needle = search.casefold()
    return [row for row in rows if _row_matches(row, needle)]


def _row_matches(row: dict[str, object], needle: str) -> bool:
    return any(needle in str(value).casefold() for value in row.values())


def _json_row(row: dict[str, object]) -> dict[str, object]:
    return {key: _json_value(value) for key, value in row.items()}


def _json_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _columns(rows: list[dict[str, object]]) -> list[str]:
    return list(rows[0].keys()) if rows else []


def _empty_rows_payload(error: str) -> dict[str, object]:
    return {"columns": [], "rows": [], "total": 0, "error": error}


def _formula_json(factor: FactorDefinition) -> str:
    payload = expression_to_dict(factor.expression)
    return json.dumps(payload, indent=2, sort_keys=True)


def _get_factor_or_404(
    registry: FactorRegistry,
    name: str,
) -> FactorDefinition:
    try:
        return registry.get_factor(name)
    except KeyError as error:
        raise Http404(f"Missing factor {name}; expected registered factor") from error


def _post_int(request: HttpRequest, name: str, default: int, limit: int) -> int:
    raw_value = request.POST.get(name, "")
    if not raw_value:
        return default
    value = _int_value(name, raw_value)
    return max(1, min(value, limit))


def _query_int(request: HttpRequest, name: str, default: int) -> int:
    raw_value = request.GET.get(name, "")
    if not raw_value:
        return default
    return _int_value(name, raw_value)


def _int_value(name: str, raw_value: str) -> int:
    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError(
            f"Invalid integer {name}={raw_value}; expected base-10 integer"
        ) from error


def _registry() -> FactorRegistry:
    return FactorRegistry(connection)


def _export_dir() -> Path:
    return Path(settings.PARQUET_EXPORT_DIR)
