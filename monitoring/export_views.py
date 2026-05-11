"""Dynamic Parquet viewer endpoints."""

from pathlib import Path

from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404

from monitoring.exporters import ParquetRows, read_parquet_rows
from monitoring.models import ExportArtifact


def parquet_rows_api(request: HttpRequest, pk: int) -> JsonResponse:
    """Return bounded Parquet rows for the dynamic table.

    Example:
        `GET /exports/1/rows/?search=OpenAI`
    """
    artifact = get_object_or_404(ExportArtifact, pk=pk)
    rows = read_parquet_rows(
        Path(artifact.path),
        page=_query_int(request, "page", 1),
        page_size=_query_int(request, "page_size", 25),
        search=request.GET.get("search", ""),
        sort=request.GET.get("sort", ""),
        direction=request.GET.get("direction", "asc"),
    )
    return JsonResponse(_rows_payload(rows))


def _query_int(request: HttpRequest, name: str, default: int) -> int:
    value = request.GET.get(name, "")
    if not value:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid query parameter {name}={value}; expected integer"
        ) from error


def _rows_payload(rows: ParquetRows) -> dict[str, object]:
    return {
        "columns": list(rows.columns),
        "rows": list(rows.rows),
        "total": rows.total,
    }
