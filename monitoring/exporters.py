"""Apache Arrow and Parquet export boundary."""

from dataclasses import dataclass
from pathlib import Path

from django.db.models import QuerySet

from monitoring.models import ExportArtifact, NormalizedDocument


@dataclass(frozen=True, slots=True)
class ParquetPreview:
    """A small Parquet table preview for UI rendering.

    Example:
        `preview = read_parquet_preview(Path("exports/documents.parquet"))`
    """

    columns: tuple[str, ...]
    rows: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class ParquetRows:
    """Searchable Parquet rows for the dynamic viewer.

    Example:
        `rows = read_parquet_rows(Path("exports/documents.parquet"))`
    """

    columns: tuple[str, ...]
    rows: tuple[dict[str, object], ...]
    total: int


class ArrowTableWriter:
    """Thin wrapper around Apache Arrow table and Parquet writes.

    Example:
        `ArrowTableWriter().write_parquet(rows, Path("documents.parquet"))`
    """

    def write_parquet(self, rows: list[dict[str, object]], output_path: Path) -> Path:
        """Write rows to a Parquet file.

        Example:
            `writer.write_parquet(rows, Path("exports/documents.parquet"))`
        """
        pyarrow, parquet = _arrow_modules()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        table = pyarrow.Table.from_pylist(rows)
        parquet.write_table(table, output_path)
        return output_path


def export_documents_to_parquet(
    output_path: Path,
    queryset: QuerySet[NormalizedDocument] | None = None,
) -> Path:
    """Export normalized documents to a Parquet dataset.

    Example:
        `export_documents_to_parquet(Path("exports/documents.parquet"))`
    """
    documents = queryset or NormalizedDocument.objects.select_related("source").all()
    rows = [document_to_export_row(document) for document in documents]
    return ArrowTableWriter().write_parquet(rows, output_path)


def export_documents_artifact(
    output_path: Path,
    queryset: QuerySet[NormalizedDocument] | None = None,
) -> ExportArtifact:
    """Export documents and persist artifact metadata.

    Example:
        `artifact = export_documents_artifact(Path("exports/documents.parquet"))`
    """
    documents = queryset or NormalizedDocument.objects.select_related("source").all()
    rows = [document_to_export_row(document) for document in documents]
    written_path = ArrowTableWriter().write_parquet(rows, output_path)
    return _upsert_export_artifact(written_path, rows)


def read_parquet_preview(output_path: Path, limit: int = 25) -> ParquetPreview:
    """Read a bounded Parquet preview for dashboard rendering.

    Example:
        `preview = read_parquet_preview(Path("exports/documents.parquet"), 10)`
    """
    if not output_path.exists():
        raise RuntimeError(f"Parquet preview failed for {output_path}; expected file")
    _pyarrow, parquet = _arrow_modules()
    table = parquet.read_table(output_path).slice(0, limit)
    columns = tuple(table.column_names)
    rows = tuple(table.to_pylist())
    return ParquetPreview(columns=columns, rows=rows)


def read_parquet_rows(
    output_path: Path,
    page: int = 1,
    page_size: int = 25,
    search: str = "",
    sort: str = "",
    direction: str = "asc",
) -> ParquetRows:
    """Read filtered and sorted Parquet rows for the viewer.

    Example:
        `rows = read_parquet_rows(path, search="OpenAI")`
    """
    preview = read_parquet_preview(output_path, limit=1000)
    filtered_rows = _filter_rows(list(preview.rows), search)
    sorted_rows = _sort_rows(filtered_rows, sort, direction)
    start = max(0, page - 1) * page_size
    page_rows = tuple(sorted_rows[start : start + page_size])
    return ParquetRows(preview.columns, page_rows, len(filtered_rows))


def document_to_export_row(document: NormalizedDocument) -> dict[str, object]:
    """Convert one normalized document to an Arrow-friendly row.

    Example:
        `row = document_to_export_row(document)`
    """
    return {
        "id": document.id,
        "source_id": document.source_id,
        "source_name": document.source.name,
        "canonical_url": document.canonical_url,
        "title": document.title,
        "author": document.author,
        "published_at": document.published_at,
        "language": document.language,
        "content": document.content,
        "entities": document.entities,
        "tags": document.tags,
        "dedupe_hash": document.dedupe_hash,
    }


def _arrow_modules() -> tuple[object, object]:
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError as error:
        raise RuntimeError(_missing_arrow_error()) from error
    return pyarrow, pyarrow.parquet


def _missing_arrow_error() -> str:
    return "Arrow export failed; expected pyarrow to be installed"


def _upsert_export_artifact(
    output_path: Path,
    rows: list[dict[str, object]],
) -> ExportArtifact:
    artifact, _created = ExportArtifact.objects.update_or_create(
        path=str(output_path),
        defaults=_artifact_defaults(output_path, rows),
    )
    return artifact


def _artifact_defaults(
    output_path: Path,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "export_type": "documents",
        "row_count": len(rows),
        "byte_size": output_path.stat().st_size if output_path.exists() else 0,
        "schema": _schema_from_rows(rows),
    }


def _schema_from_rows(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    if not rows:
        return []
    first_row = rows[0]
    return [
        {"name": key, "type": type(value).__name__} for key, value in first_row.items()
    ]


def _filter_rows(rows: list[dict[str, object]], search: str) -> list[dict[str, object]]:
    if not search:
        return rows
    lowered = search.lower()
    return [
        row
        for row in rows
        if lowered in " ".join(str(value).lower() for value in row.values())
    ]


def _sort_rows(
    rows: list[dict[str, object]],
    sort: str,
    direction: str,
) -> list[dict[str, object]]:
    if not sort:
        return rows
    reverse = direction == "desc"
    return sorted(rows, key=lambda row: str(row.get(sort, "")), reverse=reverse)
