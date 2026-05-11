"""Headless browser fetcher for public pages that require rendering."""

from collections.abc import Mapping
from datetime import UTC, datetime

from monitoring.contracts import FetchRequest, FetchResult
from monitoring.fetchers.rate_limit import wait_for_source_rate_limit
from monitoring.fetchers.robots import RobotsGuard


class HeadlessBrowserFetcher:
    """Fetch a public page using Playwright when JavaScript rendering is needed.

    Example:
        `HeadlessBrowserFetcher().fetch(FetchRequest(source_id=1, url=url, user_agent=ua))`
    """

    def fetch(self, request: FetchRequest) -> FetchResult:
        """Render a public page after robots.txt allows the URL.

        Example:
            `result = fetcher.fetch(request)`
        """
        wait_for_source_rate_limit(request)
        _ensure_robots_allowed(request)
        return _fetch_with_playwright(request)


def _ensure_robots_allowed(request: FetchRequest) -> None:
    if request.respect_robots:
        RobotsGuard(request.user_agent).ensure_allowed(request.url)


def _fetch_with_playwright(request: FetchRequest) -> FetchResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError(_missing_playwright_error(request.url)) from error
    with sync_playwright() as playwright:
        return _render_page(playwright, request)


def _render_page(playwright: object, request: FetchRequest) -> FetchResult:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(user_agent=request.user_agent)
    response = page.goto(request.url, wait_until="networkidle")
    body = page.content()
    status_code = _response_status(response)
    content_type = _response_content_type(response)
    browser.close()
    return _browser_result(request.url, status_code, body, content_type)


def _browser_result(
    url: str, status_code: int, body: str, content_type: str
) -> FetchResult:
    return FetchResult(
        url=url,
        status_code=status_code,
        body=body,
        content_type=content_type,
        headers={},
        fetched_at=datetime.now(UTC),
    )


def _response_status(response: object | None) -> int:
    if response is None:
        return 200
    return int(getattr(response, "status", 200))


def _response_content_type(response: object | None) -> str:
    if response is None:
        return "text/html"
    headers = getattr(response, "headers", {})
    if isinstance(headers, Mapping):
        return str(headers.get("content-type", "text/html"))
    return "text/html"


def _missing_playwright_error(url: str) -> str:
    return (
        f"Browser fetch failed for URL {url!r}; expected Playwright to be installed "
        "with a Chromium runtime"
    )
