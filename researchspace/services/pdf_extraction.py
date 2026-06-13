"""PDF ingestion and optional PyMuPDF extraction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from django.core.files.uploadedfile import UploadedFile

from sourceflow.config.feature_flags import require_feature


class DependencyUnavailable(RuntimeError):
    """Raised when an optional ResearchSpace dependency is not installed."""


@dataclass(frozen=True, slots=True)
class PaperIngestResult:
    """Result returned when a PDF upload is stored or deduplicated."""

    paper: object
    duplicate: bool
    message: str


@dataclass(frozen=True, slots=True)
class PdfExtractionResult:
    """Extracted page text or a clear dependency message."""

    pages: list[tuple[int, str]]
    message: str


def ingest_uploaded_pdf(title: str, uploaded_file: UploadedFile) -> PaperIngestResult:
    """Store a PDF as a local Paper, deduplicated by SHA-256.

    Example:
        `ingest_uploaded_pdf("Paper", uploaded_file)`
    """
    require_feature("RESEARCHSPACE_PDF_UPLOAD")
    from researchspace.models import Paper

    digest = uploaded_file_sha256(uploaded_file)
    existing = Paper.objects.filter(sha256=digest).first()
    if existing is not None:
        return PaperIngestResult(existing, True, "Duplicate PDF hash detected")
    paper = Paper.objects.create(
        title=title.strip() or uploaded_file.name,
        original_filename=uploaded_file.name,
        sha256=digest,
        mime_type=getattr(uploaded_file, "content_type", ""),
    )
    paper.pdf_file.save(uploaded_file.name, uploaded_file, save=True)
    return PaperIngestResult(paper, False, "Paper uploaded")


def extract_pdf_pages(path: str | Path) -> PdfExtractionResult:
    """Extract page text with PyMuPDF when available.

    Example:
        `extract_pdf_pages("paper.pdf")`
    """
    require_feature("RESEARCHSPACE_PYMUPDF_EXTRACTION")
    try:
        import fitz
    except ImportError:
        return PdfExtractionResult([], "PyMuPDF is required for PDF text extraction")
    pages = _extract_with_fitz(fitz, Path(path))
    return PdfExtractionResult(pages, f"Extracted {len(pages)} page(s)")


def uploaded_file_sha256(uploaded_file: UploadedFile) -> str:
    """Hash an uploaded file without consuming it permanently.

    Example:
        `digest = uploaded_file_sha256(uploaded_file)`
    """
    position = uploaded_file.tell()
    uploaded_file.seek(0)
    digest = _stream_sha256(uploaded_file)
    uploaded_file.seek(position)
    return digest


def _stream_sha256(stream: BinaryIO) -> str:
    hasher = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        hasher.update(chunk)
    return hasher.hexdigest()


def _extract_with_fitz(fitz_module: object, path: Path) -> list[tuple[int, str]]:
    document = fitz_module.open(path)
    pages: list[tuple[int, str]] = []
    for page_index in range(document.page_count):
        text = document.load_page(page_index).get_text("text")
        pages.append((page_index + 1, str(text).strip()))
    document.close()
    return pages
