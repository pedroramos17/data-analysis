"""Catalog synchronization services for source registry rows."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from monitoring.catalog import (
    DEFAULT_ALLOWED_DOMAINS,
    DEFAULT_FEED_CATALOG,
    FeedCatalogRow,
    load_feed_catalog,
    upsert_catalog_sources,
)
from monitoring.dashboard_models import DashboardSetting


CATALOG_SYNC_SETTING_KEY = "catalog_sync.worldmonitor_feeds"


@dataclass(frozen=True, slots=True)
class CatalogSyncResult:
    """Summary for one catalog synchronization run.

    Example:
        `result = sync_worldmonitor_feeds(dry_run=True)`
    """

    catalog_name: str
    source_count: int
    dry_run: bool
    changed: bool
    catalog_hash: str


def sync_catalogs(feeds: bool = True, dry_run: bool = False) -> tuple[CatalogSyncResult, ...]:
    """Synchronize selected bundled JSON catalogs.

    Example:
        `results = sync_catalogs(feeds=True, dry_run=False)`
    """
    results = []
    if feeds:
        results.append(sync_worldmonitor_feeds(dry_run=dry_run))
    return tuple(results)


def sync_worldmonitor_feeds(
    dry_run: bool = False,
    catalog_path: Path = DEFAULT_FEED_CATALOG,
    allowed_domains_path: Path = DEFAULT_ALLOWED_DOMAINS,
) -> CatalogSyncResult:
    """Validate and optionally upsert WorldMonitor source rows.

    Example:
        `sync_worldmonitor_feeds(dry_run=True)`
    """
    rows = load_feed_catalog(catalog_path, allowed_domains_path)
    catalog_hash = _catalog_hash(catalog_path, allowed_domains_path)
    changed = _catalog_changed(CATALOG_SYNC_SETTING_KEY, catalog_hash)
    source_count = len(rows) if dry_run else _sync_rows(rows)
    if not dry_run:
        _record_sync_result(source_count, catalog_hash)
    return CatalogSyncResult("worldmonitor_feeds", source_count, dry_run, changed, catalog_hash)


def ensure_catalogs_synced_if_enabled() -> CatalogSyncResult | None:
    """Sync catalogs on dashboard load only when the opt-in setting is enabled.

    Example:
        `ensure_catalogs_synced_if_enabled()`
    """
    if not getattr(settings, "MONITOR_AUTOLOAD_CATALOGS", False):
        return None
    try:
        if not _catalog_changed(CATALOG_SYNC_SETTING_KEY, _default_catalog_hash()):
            return None
        return sync_worldmonitor_feeds(dry_run=False)
    except Exception:
        return None


def _sync_rows(rows: list[FeedCatalogRow]) -> int:
    return upsert_catalog_sources(rows)


def _default_catalog_hash() -> str:
    return _catalog_hash(DEFAULT_FEED_CATALOG, DEFAULT_ALLOWED_DOMAINS)


def _catalog_hash(catalog_path: Path, allowed_domains_path: Path) -> str:
    digest = sha256()
    for path in (catalog_path, allowed_domains_path):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _catalog_changed(setting_key: str, catalog_hash: str) -> bool:
    setting = DashboardSetting.objects.filter(key=setting_key).first()
    if setting is None:
        return True
    return setting.value_json.get("catalog_hash") != catalog_hash


def _record_sync_result(source_count: int, catalog_hash: str) -> None:
    DashboardSetting.objects.update_or_create(
        key=CATALOG_SYNC_SETTING_KEY,
        defaults={
            "value_json": {
                "catalog_hash": catalog_hash,
                "source_count": source_count,
                "synced_at": timezone.now().isoformat(),
            }
        },
    )
