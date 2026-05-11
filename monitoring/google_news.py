"""Google News RSS topic source helpers."""

from urllib.parse import urlencode

from monitoring.models import Source

GOOGLE_NEWS_TEMPLATE = "https://news.google.com/rss/search?{query_string}"


def build_google_news_url(query: str) -> str:
    """Build a Google News RSS search URL.

    Example:
        `build_google_news_url("open source intelligence")`
    """
    query_string = urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return GOOGLE_NEWS_TEMPLATE.format(query_string=query_string)


def create_google_news_source(
    query: str,
    category: str,
    tags: tuple[str, ...],
) -> Source:
    """Create or update a dynamic Google News RSS source.

    Example:
        `create_google_news_source("AI security", "technology", ("ai",))`
    """
    _validate_google_news_category(category)
    source_name = f"Google News: {query.strip()}"
    url = build_google_news_url(query)
    source, _created = Source.objects.update_or_create(
        name=source_name,
        defaults=_google_news_defaults(url, category, tags),
    )
    return source


def _google_news_defaults(
    url: str,
    category: str,
    tags: tuple[str, ...],
) -> dict[str, object]:
    return {
        "url": url,
        "source_type": Source.SourceType.RSS,
        "fetch_method": Source.FetchMethod.HTTP,
        "cadence_minutes": 30,
        "tags": list(tags),
        "category": category,
        "language": "en",
        "source_tier": 4,
        "reputation_score": 0,
        "state_affiliation": "",
        "propaganda_risk": False,
        "is_dynamic": True,
        "query_template": GOOGLE_NEWS_TEMPLATE,
        "is_enabled": True,
        "rate_limit_seconds": 10,
    }


def _validate_google_news_category(category: str) -> None:
    if category in set(Source.Category.values):
        return
    raise ValueError(
        f"Invalid category {category!r}; expected one of {list(Source.Category.values)!r}"
    )
