"""Compliance policies for financial data ingestion."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IngestionPolicy:
    """Compliance metadata required before automated ingestion.

    Example:
        `policy = IngestionPolicy("SEC", "official_api", True, 600, "...", "...")`
    """

    source_name: str
    source_type: str
    automated_access_permitted: bool
    rate_limit_per_minute: int
    user_agent_contact: str
    terms_notes: str
    attribution: str
    terms_url: str = ""
    robots_required: bool = False


def validate_public_web_policy(policy: IngestionPolicy) -> None:
    """Validate explicit permission before public web automation.

    Example:
        `validate_public_web_policy(policy)`
    """
    _require_permission(policy)
    _require_rate_limit(policy)
    _require_contact(policy)
    _require_terms(policy)
    _require_attribution(policy)


def official_api_policy(source_name: str, attribution: str) -> IngestionPolicy:
    """Build a safe policy for official API-first connectors.

    Example:
        `policy = official_api_policy("SEC EDGAR", "SEC")`
    """
    return IngestionPolicy(
        source_name=source_name,
        source_type="official_api",
        automated_access_permitted=True,
        rate_limit_per_minute=600,
        user_agent_contact="configured-by-user",
        terms_notes="Official API-first connector; review source terms.",
        attribution=attribution,
    )


def _require_permission(policy: IngestionPolicy) -> None:
    if policy.automated_access_permitted:
        return
    raise ValueError(
        f"Invalid policy automated_access_permitted=False for "
        f"{policy.source_name!r}; expected explicit permission"
    )


def _require_rate_limit(policy: IngestionPolicy) -> None:
    if policy.rate_limit_per_minute > 0:
        return
    raise ValueError(
        f"Invalid policy rate_limit_per_minute={policy.rate_limit_per_minute!r} "
        f"for {policy.source_name!r}; expected positive integer"
    )


def _require_contact(policy: IngestionPolicy) -> None:
    if policy.user_agent_contact.strip():
        return
    raise ValueError(
        f"Invalid policy user_agent_contact={policy.user_agent_contact!r} "
        f"for {policy.source_name!r}; expected contact text"
    )


def _require_terms(policy: IngestionPolicy) -> None:
    if policy.terms_notes.strip():
        return
    raise ValueError(
        f"Invalid policy terms_notes={policy.terms_notes!r} "
        f"for {policy.source_name!r}; expected source-specific notes"
    )


def _require_attribution(policy: IngestionPolicy) -> None:
    if policy.attribution.strip():
        return
    raise ValueError(
        f"Invalid policy attribution={policy.attribution!r} "
        f"for {policy.source_name!r}; expected attribution text"
    )
