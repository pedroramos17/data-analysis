"""Policy gates for vendor-authorized market data ingestion."""

from __future__ import annotations

from collections.abc import Mapping

ALLOWED_INGESTION_MODES = frozenset(
    {
        "public_api",
        "licensed_api",
        "broker_export",
        "exchange_file",
        "manual_csv",
        "local_jsonl",
        "research_snapshot",
        "vendor_authorized_browser",
        "vendor_oauth",
        "vendor_authorized_proxy",
    }
)
FORBIDDEN_INGESTION_MODES = frozenset(
    {
        "residential_proxy",
        "proxy_rotation_for_evasion",
        "bypass_paywall",
        "bypass_login",
        "bypass_antibot",
        "scrape_tradingview_realtime",
        "reuse_user_session_cookies",
    }
)
VENDOR_AUTHORIZED_MODES = frozenset(
    {"vendor_authorized_browser", "vendor_oauth", "vendor_authorized_proxy"}
)
AUTHORIZED_CONFIG_KEYS = frozenset(
    {
        "vendor",
        "authorization_basis",
        "storage_state_path",
        "capture_url",
        "proxy_url",
    }
)


def validate_ingestion_mode(mode: str) -> str:
    """Return a known compliant ingestion mode or fail fast.

    Example:
        `safe_mode = validate_ingestion_mode("local_jsonl")`
    """
    normalized = mode.strip()
    if normalized in ALLOWED_INGESTION_MODES:
        return normalized
    if normalized in FORBIDDEN_INGESTION_MODES:
        raise ValueError(_forbidden_mode_error(normalized))
    raise ValueError(_unknown_mode_error(normalized))


def validate_authorized_vendor_config(
    config: Mapping[str, object],
    mode: str,
) -> None:
    """Validate local vendor authorization metadata without logging secrets.

    Example:
        `validate_authorized_vendor_config(config, "vendor_authorized_browser")`
    """
    safe_mode = validate_ingestion_mode(mode)
    if safe_mode not in VENDOR_AUTHORIZED_MODES:
        return
    _reject_unknown_keys(config)
    _require_text(config, "vendor")
    _require_text(config, "authorization_basis")
    _validate_browser_config(config, safe_mode)
    _validate_proxy_config(config, safe_mode)


def _forbidden_mode_error(mode: str) -> str:
    return (
        f"Invalid ingestion mode {mode!r}; expected vendor-authorized or local "
        f"mode in {sorted(ALLOWED_INGESTION_MODES)}"
    )


def _unknown_mode_error(mode: str) -> str:
    return (
        f"Unknown ingestion mode {mode!r}; expected one of "
        f"{sorted(ALLOWED_INGESTION_MODES)}"
    )


def _reject_unknown_keys(config: Mapping[str, object]) -> None:
    unknown_keys = sorted(set(config) - AUTHORIZED_CONFIG_KEYS)
    if not unknown_keys:
        return
    raise ValueError(
        f"Invalid vendor config keys {unknown_keys!r}; expected keys "
        f"{sorted(AUTHORIZED_CONFIG_KEYS)}"
    )


def _require_text(config: Mapping[str, object], key: str) -> str:
    value = config.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(
        f"Invalid vendor config {key}={value!r}; expected non-empty string"
    )


def _validate_browser_config(config: Mapping[str, object], mode: str) -> None:
    if mode != "vendor_authorized_browser":
        return
    _require_text(config, "storage_state_path")
    _require_text(config, "capture_url")


def _validate_proxy_config(config: Mapping[str, object], mode: str) -> None:
    if mode != "vendor_authorized_proxy":
        return
    _require_text(config, "proxy_url")
