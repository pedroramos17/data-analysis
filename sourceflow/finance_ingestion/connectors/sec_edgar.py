"""SEC EDGAR official API normalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sourceflow.config.feature_flags import require_feature


def normalize_companyfacts(
    cik: str,
    payload: Mapping[str, object],
    forms: Iterable[str] | None = None,
) -> list[dict[str, object]]:
    """Flatten SEC companyfacts payloads into fundamental fact rows.

    Example:
        `rows = normalize_companyfacts("0000320193", payload, {"10-K"})`
    """
    require_feature("FIN_DATA_SEC_EDGAR")
    allowed_forms = {form.strip() for form in forms or [] if form.strip()}
    rows: list[dict[str, object]] = []
    for taxonomy, tags in _facts(payload).items():
        rows.extend(_taxonomy_rows(cik, taxonomy, tags, allowed_forms))
    return rows


def normalize_companyconcept(
    cik: str,
    taxonomy: str,
    tag: str,
    payload: Mapping[str, object],
) -> list[dict[str, object]]:
    """Flatten one SEC companyconcept response.

    Example:
        `rows = normalize_companyconcept(cik, "us-gaap", "Assets", payload)`
    """
    require_feature("FIN_DATA_SEC_EDGAR")
    concept = {"units": payload.get("units", {})}
    return _tag_rows(cik, taxonomy, tag, concept, set())


def normalize_frames(
    taxonomy: str,
    tag: str,
    payload: Mapping[str, object],
) -> list[dict[str, object]]:
    """Normalize SEC frames rows without issuer lookup.

    Example:
        `rows = normalize_frames("us-gaap", "Assets", payload)`
    """
    require_feature("FIN_DATA_SEC_EDGAR")
    items = payload.get("data", [])
    if not isinstance(items, list):
        return []
    return [_frame_row(taxonomy, tag, item) for item in items if isinstance(item, dict)]


def submission_urls(cik: str) -> dict[str, str]:
    """Return official SEC URL templates for a normalized CIK.

    Example:
        `urls = submission_urls("320193")`
    """
    require_feature("FIN_DATA_SEC_EDGAR")
    normalized = cik.zfill(10)
    return {
        "submissions": f"https://data.sec.gov/submissions/CIK{normalized}.json",
        "companyfacts": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalized}.json",
    }


def _facts(payload: Mapping[str, object]) -> dict[str, object]:
    facts = payload.get("facts", {})
    return facts if isinstance(facts, dict) else {}


def _taxonomy_rows(
    cik: str,
    taxonomy: str,
    tags: object,
    allowed_forms: set[str],
) -> list[dict[str, object]]:
    if not isinstance(tags, dict):
        return []
    rows: list[dict[str, object]] = []
    for tag, concept in tags.items():
        rows.extend(_tag_rows(cik, taxonomy, str(tag), concept, allowed_forms))
    return rows


def _tag_rows(
    cik: str,
    taxonomy: str,
    tag: str,
    concept: object,
    allowed_forms: set[str],
) -> list[dict[str, object]]:
    if not isinstance(concept, dict):
        return []
    rows: list[dict[str, object]] = []
    for unit, facts in _units(concept).items():
        rows.extend(_unit_rows(cik, taxonomy, tag, str(unit), facts, allowed_forms))
    return rows


def _units(concept: Mapping[str, object]) -> dict[str, object]:
    units = concept.get("units", {})
    return units if isinstance(units, dict) else {}


def _unit_rows(
    cik: str,
    taxonomy: str,
    tag: str,
    unit: str,
    facts: object,
    allowed_forms: set[str],
) -> list[dict[str, object]]:
    if not isinstance(facts, list):
        return []
    return [
        _fact_row(cik, taxonomy, tag, unit, fact)
        for fact in facts
        if _fact_is_allowed(fact, allowed_forms)
    ]


def _fact_is_allowed(fact: object, allowed_forms: set[str]) -> bool:
    return isinstance(fact, dict) and (
        not allowed_forms or str(fact.get("form", "")) in allowed_forms
    )


def _fact_row(
    cik: str,
    taxonomy: str,
    tag: str,
    unit: str,
    fact: Mapping[str, object],
) -> dict[str, object]:
    return {
        "cik": cik,
        "taxonomy": taxonomy,
        "tag": tag,
        "unit": unit,
        "fiscal_year": fact.get("fy"),
        "fiscal_period": fact.get("fp", ""),
        "start_date": fact.get("start"),
        "end_date": fact.get("end"),
        "filed_at": fact.get("filed"),
        "value": _numeric(fact.get("val")),
        "form_type": fact.get("form", ""),
        "accession_number": fact.get("accn", ""),
        "raw_payload_json": dict(fact),
    }


def _frame_row(
    taxonomy: str,
    tag: str,
    item: Mapping[str, object],
) -> dict[str, object]:
    return {
        "cik": str(item.get("cik", "")),
        "taxonomy": taxonomy,
        "tag": tag,
        "unit": str(item.get("uom", "")),
        "fiscal_year": item.get("fy"),
        "fiscal_period": item.get("fp", ""),
        "end_date": item.get("end"),
        "value": _numeric(item.get("val")),
        "form_type": item.get("form", ""),
        "accession_number": item.get("accn", ""),
        "raw_payload_json": dict(item),
    }


def _numeric(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value).replace(",", ""))
