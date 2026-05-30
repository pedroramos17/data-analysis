"""Export QuantSpace chunks to local Parquet artifacts."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from sourceflow.config.feature_flags import require_feature


def export_paper_chunks_to_parquet(paper: object) -> object:
    """Write paper chunks to Parquet and store a PaperArtifact pointer.

    Example:
        `export_paper_chunks_to_parquet(paper)`
    """
    require_feature("QUANTSPACE_PARQUET_EXPORT")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError(
            "pyarrow is required for QuantSpace Parquet export"
        ) from error
    path = _chunk_export_path(paper)
    table = pa.Table.from_pylist(_chunk_rows(paper))
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return _create_artifact(paper, path)


def _chunk_rows(paper: object) -> list[dict[str, object]]:
    return [
        {
            "paper_id": paper.id,
            "chunk_index": chunk.chunk_index,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "text": chunk.text,
            "support_status": chunk.support_status,
        }
        for chunk in paper.chunks.all()
    ]


def _chunk_export_path(paper: object) -> Path:
    root = Path(getattr(settings, "PARQUET_EXPORT_DIR", "exports"))
    return root / "quantspace" / f"paper_{paper.id}_chunks.parquet"


def _create_artifact(paper: object, path: Path) -> object:
    from quantspace.models import PaperArtifact

    return PaperArtifact.objects.create(
        paper=paper,
        artifact_type="chunks_parquet",
        path=str(path),
        support_status="SUPPORTED",
    )
