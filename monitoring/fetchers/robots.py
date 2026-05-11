"""Robots.txt guard used before public fetching."""

from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

_ROBOTS_CACHE: dict[str, RobotFileParser] = {}


class RobotsGuard:
    """Check `robots.txt` before fetching public pages.

    Example:
        `RobotsGuard("Agent").ensure_allowed("https://example.com/")`
    """

    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._cache = _ROBOTS_CACHE

    def ensure_allowed(self, url: str) -> None:
        """Raise when robots.txt does not allow the URL.

        Example:
            `guard.ensure_allowed("https://example.com/feed.xml")`
        """
        if self.can_fetch(url):
            return
        message = _robots_error(url, self.user_agent)
        raise PermissionError(message)

    def can_fetch(self, url: str) -> bool:
        """Return whether the configured user agent may fetch a URL.

        Example:
            `guard.can_fetch("https://example.com/feed.xml")`
        """
        parser = self._parser_for(url)
        return parser.can_fetch(self.user_agent, url)

    def _parser_for(self, url: str) -> RobotFileParser:
        origin = _origin_for_url(url)
        if origin not in self._cache:
            self._cache[origin] = _read_robots_parser(origin)
        return self._cache[origin]


def _origin_for_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Invalid URL {url!r}; expected absolute URL")
    return f"{parts.scheme}://{parts.netloc}"


def _read_robots_parser(origin: str) -> RobotFileParser:
    parser = RobotFileParser()
    parser.set_url(urljoin(origin, "/robots.txt"))
    parser.read()
    return parser


def _robots_error(url: str, user_agent: str) -> str:
    return (
        f"Robots denied URL {url!r} for user agent {user_agent!r}; "
        "expected a public path allowed by robots.txt"
    )
