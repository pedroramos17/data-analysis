"""HTTP fetcher with robots checks and polite request headers."""

from datetime import UTC, datetime
from email.message import Message
from http.client import HTTPResponse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from monitoring.contracts import FetchRequest, FetchResult
from monitoring.fetchers.rate_limit import wait_for_source_rate_limit
from monitoring.fetchers.robots import RobotsGuard


class HttpFetcher:
    """Fetch public pages through standard HTTP.

    Example:
        `HttpFetcher().fetch(FetchRequest(source_id=1, url=url, user_agent=ua))`
    """

    def fetch(self, request: FetchRequest) -> FetchResult:
        """Fetch a URL after checking robots.txt.

        Example:
            `result = fetcher.fetch(request)`
        """
        wait_for_source_rate_limit(request)
        _ensure_robots_allowed(request)
        http_request = _build_request(request)
        return _open_request(http_request, request)


def _ensure_robots_allowed(request: FetchRequest) -> None:
    if request.respect_robots:
        RobotsGuard(request.user_agent).ensure_allowed(request.url)


def _build_request(request: FetchRequest) -> Request:
    headers = {"User-Agent": request.user_agent, **dict(request.headers)}
    return Request(request.url, headers=headers, method="GET")


def _open_request(http_request: Request, request: FetchRequest) -> FetchResult:
    try:
        with urlopen(http_request, timeout=request.timeout_seconds) as response:
            return _result_from_response(request.url, response.status, response)
    except HTTPError as error:
        return _result_from_response(request.url, error.code, error)
    except URLError as error:
        message = _network_error(request.url, str(error.reason))
        raise RuntimeError(message) from error


def _result_from_response(
    url: str,
    status_code: int,
    response: HTTPResponse | HTTPError,
) -> FetchResult:
    body = response.read().decode(_charset(response.headers), errors="replace")
    return FetchResult(
        url=url,
        status_code=status_code,
        body=body,
        content_type=response.headers.get("content-type", ""),
        headers=dict(response.headers.items()),
        fetched_at=datetime.now(UTC),
    )


def _charset(headers: Message) -> str:
    content_type = headers.get_content_charset()
    return content_type or "utf-8"


def _network_error(url: str, reason: str) -> str:
    return f"Fetch failed for URL {url!r} with reason {reason!r}; expected reachable public URL"
