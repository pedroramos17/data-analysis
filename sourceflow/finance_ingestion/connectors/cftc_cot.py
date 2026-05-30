"""CFTC Commitments of Traders normalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sourceflow.config.feature_flags import require_feature


def normalize_cot_rows(
    rows: Iterable[Mapping[str, object]],
    report_type: str,
) -> list[dict[str, object]]:
    """Normalize current or historical CFTC COT rows.

    Example:
        `rows = normalize_cot_rows(csv_rows, "futures_options")`
    """
    require_feature("FIN_DATA_CFTC_COT")
    return [_cot_row(row, report_type) for row in rows]


def _cot_row(row: Mapping[str, object], report_type: str) -> dict[str, object]:
    return {
        "market_name": _text(row, "Market_and_Exchange_Names"),
        "cftc_contract_market_code": _text(row, "CFTC_Contract_Market_Code"),
        "report_date": _text(row, "Report_Date_as_YYYY-MM-DD"),
        "report_type": report_type,
        "producer_merchant_long": _number(row, "Prod_Merc_Positions_Long_ALL"),
        "producer_merchant_short": _number(row, "Prod_Merc_Positions_Short_ALL"),
        "managed_money_long": _number(row, "M_Money_Positions_Long_All"),
        "managed_money_short": _number(row, "M_Money_Positions_Short_All"),
        "swap_dealer_long": _number(row, "Swap_Positions_Long_All"),
        "swap_dealer_short": _number(row, "Swap__Positions_Short_All"),
        "open_interest": _number(row, "Open_Interest_All"),
        "raw_payload_json": dict(row),
    }


def _text(row: Mapping[str, object], key: str) -> str:
    return str(row.get(key, "")).strip()


def _number(row: Mapping[str, object], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    return float(str(value).replace(",", ""))
