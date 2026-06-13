"""Past-only missing-value handling for preprocessing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def mark_missing_ohlcv(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Flag rows that have missing OHLCV values."""
    marked: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["missing_ohlcv"] = any(_missing(item.get(column)) for column in OHLCV_COLUMNS)
        marked.append(item)
    return marked


def impute_missing_bars(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Fill missing OHLCV values from the previous row only.

    This avoids future leakage by never looking ahead.
    """
    output: list[dict[str, object]] = []
    previous_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for row in sorted(rows, key=_sort_key):
        item = dict(row)
        original_missing = bool(item.get("missing_ohlcv", False))
        key = (str(item.get("symbol") or ""), str(item.get("timeframe") or ""))
        previous = previous_by_key.get(key)
        if previous is not None:
            previous_close = previous.get("close")
            for column in ("open", "high", "low", "close"):
                if _missing(item.get(column)) and previous_close is not None:
                    item[column] = previous_close
                    item["imputed"] = True
            if _missing(item.get("volume")):
                item["volume"] = 0.0
                item["imputed"] = True
        item["missing_ohlcv"] = original_missing or any(
            _missing(item.get(column)) for column in OHLCV_COLUMNS
        )
        output.append(item)
        previous_by_key[key] = item
    return output


def _sort_key(row: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol") or ""),
        str(row.get("timeframe") or ""),
        str(row.get("ts") or ""),
    )


def _missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
