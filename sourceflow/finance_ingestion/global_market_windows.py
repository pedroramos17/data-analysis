"""Static global market session windows without heavy calendar dependencies."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from sourceflow.config.feature_flags import require_feature

EXCHANGE_WINDOWS: dict[str, dict[str, str]] = {
    "NYSE": {
        "mic": "XNYS",
        "timezone": "America/New_York",
        "open": "09:30",
        "close": "16:00",
    },
    "NASDAQ": {
        "mic": "XNAS",
        "timezone": "America/New_York",
        "open": "09:30",
        "close": "16:00",
    },
    "CME": {
        "mic": "XCME",
        "timezone": "America/Chicago",
        "open": "08:30",
        "close": "15:15",
    },
    "CBOE": {
        "mic": "XCBO",
        "timezone": "America/Chicago",
        "open": "08:30",
        "close": "15:00",
    },
    "LSE": {
        "mic": "XLON",
        "timezone": "Europe/London",
        "open": "08:00",
        "close": "16:30",
    },
    "XETRA": {
        "mic": "XETR",
        "timezone": "Europe/Berlin",
        "open": "09:00",
        "close": "17:30",
    },
    "B3": {
        "mic": "BVMF",
        "timezone": "America/Sao_Paulo",
        "open": "10:00",
        "close": "17:00",
    },
    "TSE": {"mic": "XTKS", "timezone": "Asia/Tokyo", "open": "09:00", "close": "15:00"},
    "HKEX": {
        "mic": "XHKG",
        "timezone": "Asia/Hong_Kong",
        "open": "09:30",
        "close": "16:00",
    },
    "SSE": {
        "mic": "XSHG",
        "timezone": "Asia/Shanghai",
        "open": "09:30",
        "close": "15:00",
    },
    "SZSE": {
        "mic": "XSHE",
        "timezone": "Asia/Shanghai",
        "open": "09:30",
        "close": "15:00",
    },
}


def assign_market_session(timestamp: datetime, exchange: str) -> dict[str, object]:
    """Assign a UTC timestamp to a local exchange session.

    Example:
        `session = assign_market_session(ts, "NYSE")`
    """
    require_feature("FIN_DATA_GLOBAL_MARKET_WINDOWS")
    window = _window_for(exchange)
    local_timestamp = timestamp.astimezone(ZoneInfo(window["timezone"]))
    session_type = _session_type(local_timestamp, window)
    return _session_row(exchange, window, local_timestamp, session_type)


def market_windows() -> list[dict[str, str]]:
    """Return built-in exchange window definitions.

    Example:
        `rows = market_windows()`
    """
    require_feature("FIN_DATA_GLOBAL_MARKET_WINDOWS")
    return [dict(value, exchange=key) for key, value in EXCHANGE_WINDOWS.items()]


def _window_for(exchange: str) -> dict[str, str]:
    key = exchange.strip().upper()
    if key in EXCHANGE_WINDOWS:
        return EXCHANGE_WINDOWS[key]
    raise ValueError(
        f"Invalid exchange {exchange!r}; expected one of {sorted(EXCHANGE_WINDOWS)}"
    )


def _session_type(local_timestamp: datetime, window: dict[str, str]) -> str:
    if local_timestamp.weekday() >= 5:
        return "closed"
    if _clock(window["open"]) <= local_timestamp.time() <= _clock(window["close"]):
        return "regular"
    return "closed"


def _session_row(
    exchange: str,
    window: dict[str, str],
    local_timestamp: datetime,
    session_type: str,
) -> dict[str, object]:
    return {
        "exchange": exchange.strip().upper(),
        "mic": window["mic"],
        "timezone": window["timezone"],
        "local_date": local_timestamp.date().isoformat(),
        "local_time": local_timestamp.time().isoformat(),
        "session_type": session_type,
    }


def _clock(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))
