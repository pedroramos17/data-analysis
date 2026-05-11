"""Validation and loading for curated RSS feed catalogs."""

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

from monitoring.models import Source

CATALOG_DIR = Path(settings.BASE_DIR) / "monitoring" / "catalogs"
DEFAULT_FEED_CATALOG = CATALOG_DIR / "worldmonitor_feeds.json"
DEFAULT_ALLOWED_DOMAINS = CATALOG_DIR / "rss_allowed_domains.json"


@dataclass(frozen=True, slots=True)
class FeedCatalogRow:
    """Validated source catalog row.

    Example:
        `FeedCatalogRow(name="BBC", url="https://feeds.bbci.co.uk/news/rss.xml")`
    """

    name: str
    url: str
    category: str
    tags: tuple[str, ...]
    source_tier: int
    language: str
    cadence_minutes: int
    rate_limit_seconds: int
    reputation_score: float
    state_affiliation: str
    propaganda_risk: bool


def load_feed_catalog(
    catalog_path: Path = DEFAULT_FEED_CATALOG,
    allowed_domains_path: Path = DEFAULT_ALLOWED_DOMAINS,
) -> list[FeedCatalogRow]:
    """Load and validate a curated RSS feed catalog.

    Example:
        `rows = load_feed_catalog()`
    """
    allowed_domains = load_allowed_domains(allowed_domains_path)
    payload = _read_json_list(catalog_path)
    rows = [_catalog_row_from_mapping(row, catalog_path) for row in payload]
    validate_feed_catalog(rows, allowed_domains)
    return rows


def load_allowed_domains(path: Path = DEFAULT_ALLOWED_DOMAINS) -> tuple[str, ...]:
    """Load allowed feed domains from JSON.

    Example:
        `domains = load_allowed_domains()`
    """
    domains = _read_json_list(path)
    return tuple(_domain_value(domain, path) for domain in domains)


def validate_feed_catalog(
    rows: list[FeedCatalogRow],
    allowed_domains: tuple[str, ...],
) -> None:
    """Validate feed URLs, categories, tiers, and uniqueness.

    Example:
        `validate_feed_catalog(rows, ("example.org",))`
    """
    _validate_unique_names(rows)
    _validate_unique_urls(rows)
    for row in rows:
        _validate_category(row.category)
        _validate_tier(row.source_tier)
        _validate_allowed_domain(row.url, allowed_domains)


def upsert_catalog_sources(rows: list[FeedCatalogRow]) -> int:
    """Create or update source registry rows from a feed catalog.

    Example:
        `count = upsert_catalog_sources(load_feed_catalog())`
    """
    for row in rows:
        Source.objects.update_or_create(name=row.name, defaults=_source_defaults(row))
    return len(rows)


def _catalog_row_from_mapping(value: object, path: Path) -> FeedCatalogRow:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid catalog row {value!r} in {path!s}; expected object")
    return FeedCatalogRow(
        name=_string_field(value, "name", path),
        url=_string_field(value, "url", path),
        category=_string_field(value, "category", path),
        tags=_tags_field(value, path),
        source_tier=_int_field(value, "source_tier", path),
        language=_string_field(value, "language", path, "en"),
        cadence_minutes=_int_field(value, "cadence_minutes", path, 60),
        rate_limit_seconds=_int_field(value, "rate_limit_seconds", path, 10),
        reputation_score=_float_field(value, "reputation_score", path, 0.0),
        state_affiliation=_string_field(value, "state_affiliation", path, ""),
        propaganda_risk=_bool_field(value, "propaganda_risk", path, False),
    )


def _source_defaults(row: FeedCatalogRow) -> dict[str, object]:
    return {
        "url": row.url,
        "source_type": Source.SourceType.RSS,
        "fetch_method": Source.FetchMethod.HTTP,
        "cadence_minutes": row.cadence_minutes,
        "tags": list(row.tags),
        "category": row.category,
        "language": row.language,
        "source_kind": _source_kind(row),
        "source_tier": row.source_tier,
        "reputation_score": row.reputation_score,
        "reliability_score": row.reputation_score,
        "state_affiliation": row.state_affiliation,
        "propaganda_risk": row.propaganda_risk,
        "is_dynamic": False,
        "query_template": "",
        "is_enabled": True,
        "rate_limit_seconds": row.rate_limit_seconds,
    }


def _source_kind(row: FeedCatalogRow) -> str:
    if "research" in row.tags or row.category == Source.Category.SCIENCE:
        return Source.SourceKind.PAPER
    if row.category in {Source.Category.POLICY, Source.Category.DEFENSE}:
        return Source.SourceKind.GOV
    return Source.SourceKind.NEWS


def _read_json_list(path: Path) -> list[object]:
    with path.open(encoding="utf-8") as json_file:
        payload = json.load(json_file)
    if not isinstance(payload, list):
        raise ValueError(f"Invalid JSON file {path!s}; expected list")
    return payload


def _domain_value(value: object, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid allowed domain {value!r} in {path!s}; expected text")
    return _strip_www(value.strip().lower())


def _string_field(
    row: dict[object, object],
    key: str,
    path: Path,
    default: str | None = None,
) -> str:
    value = row.get(key, default)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if default is not None:
        return default
    raise ValueError(f"Invalid catalog field {key!r} in {path!s}; expected text")


def _int_field(
    row: dict[object, object],
    key: str,
    path: Path,
    default: int | None = None,
) -> int:
    value = row.get(key, default)
    if isinstance(value, int):
        return value
    raise ValueError(f"Invalid catalog field {key!r} in {path!s}; expected integer")


def _float_field(
    row: dict[object, object],
    key: str,
    path: Path,
    default: float,
) -> float:
    value = row.get(key, default)
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"Invalid catalog field {key!r} in {path!s}; expected number")


def _bool_field(
    row: dict[object, object],
    key: str,
    path: Path,
    default: bool,
) -> bool:
    value = row.get(key, default)
    if isinstance(value, bool):
        return value
    raise ValueError(f"Invalid catalog field {key!r} in {path!s}; expected boolean")


def _tags_field(row: dict[object, object], path: Path) -> tuple[str, ...]:
    value = row.get("tags", [])
    if not isinstance(value, list):
        raise ValueError(f"Invalid catalog field 'tags' in {path!s}; expected list")
    return tuple(str(tag).strip().lower() for tag in value if str(tag).strip())


def _validate_unique_names(rows: list[FeedCatalogRow]) -> None:
    names = [row.name.lower() for row in rows]
    if len(names) != len(set(names)):
        raise ValueError(f"Invalid feed catalog names {names!r}; expected unique names")


def _validate_unique_urls(rows: list[FeedCatalogRow]) -> None:
    urls = [row.url.lower() for row in rows]
    if len(urls) != len(set(urls)):
        raise ValueError(f"Invalid feed catalog URLs {urls!r}; expected unique URLs")


def _validate_category(category: str) -> None:
    allowed = set(Source.Category.values)
    if category not in allowed:
        raise ValueError(
            f"Invalid category {category!r}; expected one of {sorted(allowed)!r}"
        )


def _validate_tier(source_tier: int) -> None:
    if source_tier in {1, 2, 3, 4}:
        return
    raise ValueError(f"Invalid source tier {source_tier!r}; expected 1, 2, 3, or 4")


def _validate_allowed_domain(url: str, allowed_domains: tuple[str, ...]) -> None:
    domain = _domain_from_url(url)
    if any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in allowed_domains
    ):
        return
    raise ValueError(f"Invalid feed URL domain {domain!r}; expected allowlisted domain")


def _domain_from_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid feed URL {url!r}; expected absolute URL")
    return _strip_www(parts.netloc.lower().split(":", 1)[0])


def _strip_www(domain: str) -> str:
    if domain.startswith("www."):
        return domain[4:]
    return domain
