"""Process-local rate limiting for polite source fetches."""

import time
from threading import Lock

from monitoring.contracts import FetchRequest

_LAST_FETCH_SECONDS: dict[int, float] = {}
_RATE_LIMIT_LOCK = Lock()


def wait_for_source_rate_limit(request: FetchRequest) -> None:
    """Pause until the source-specific rate limit allows a fetch.

    Example:
        `wait_for_source_rate_limit(request)`
    """
    if request.rate_limit_seconds <= 0:
        return
    with _RATE_LIMIT_LOCK:
        wait_seconds = _remaining_wait_seconds(request, time.monotonic())
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _LAST_FETCH_SECONDS[request.source_id] = time.monotonic()


def _remaining_wait_seconds(request: FetchRequest, now_seconds: float) -> float:
    last_fetch_seconds = _LAST_FETCH_SECONDS.get(request.source_id)
    if last_fetch_seconds is None:
        return 0.0
    next_fetch_seconds = last_fetch_seconds + request.rate_limit_seconds
    return max(0.0, next_fetch_seconds - now_seconds)
