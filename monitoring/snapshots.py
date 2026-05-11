"""Raw fetch snapshot storage."""

from pathlib import Path

from django.conf import settings

from monitoring.contracts import FetchResult
from monitoring.models import Source
from monitoring.normalizers import build_content_hash


def save_fetch_snapshot(source: Source, fetch_result: FetchResult) -> str:
    """Write a raw response body once and return its media-relative path.

    Example:
        `path = save_fetch_snapshot(source, fetch_result)`
    """
    snapshot_path = _snapshot_path(source, fetch_result)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot_path.exists():
        snapshot_path.write_text(fetch_result.body, encoding="utf-8")
    return _media_relative_path(snapshot_path)


def _snapshot_path(source: Source, fetch_result: FetchResult) -> Path:
    digest = build_content_hash(fetch_result.body)
    source_part = f"source-{source.id or 'new'}"
    return Path(settings.RAW_SNAPSHOT_DIR) / source_part / f"{digest}.txt"


def _media_relative_path(snapshot_path: Path) -> str:
    try:
        return str(snapshot_path.relative_to(settings.MEDIA_ROOT))
    except ValueError:
        return str(snapshot_path)
