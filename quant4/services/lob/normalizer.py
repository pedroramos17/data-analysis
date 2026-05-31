"""Venue-neutral LOB row normalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from quant4.services.lob.parser import LOBSnapshot, PriceLevel


def normalize_lob_rows(
    rows: Iterable[Mapping[str, object]],
    venue_type: str = "generic",
) -> list[LOBSnapshot]:
    """Normalize equities, futures, crypto, or top-of-book forex rows.

    Example:
        `normalize_lob_rows(rows, venue_type="future")`
    """
    snapshots = [_normalize_lob_row(row, venue_type) for row in rows]
    return sorted(snapshots, key=lambda snapshot: snapshot.timestamp)


def _normalize_lob_row(row: Mapping[str, object], venue_type: str) -> LOBSnapshot:
    timestamp = _required_text(row, "timestamp")
    symbol = str(row.get("symbol", "UNKNOWN"))
    bids = _levels(row, "bids", "bid")
    asks = _levels(row, "asks", "ask")
    _validate_book(row, bids, asks)
    return LOBSnapshot(timestamp, symbol, bids, asks, venue_type, _metadata(row))


def _levels(
    row: Mapping[str, object],
    side_key: str,
    prefix: str,
) -> tuple[PriceLevel, ...]:
    raw_levels = row.get(side_key)
    if isinstance(raw_levels, Sequence) and not isinstance(raw_levels, str):
        return _sequence_levels(raw_levels, prefix)
    return _prefixed_levels(row, prefix)


def _sequence_levels(
    raw_levels: Sequence[object],
    prefix: str,
) -> tuple[PriceLevel, ...]:
    levels = [_level_from_sequence(level) for level in raw_levels]
    return _sort_levels([level for level in levels if level[1] > 0], prefix)


def _prefixed_levels(row: Mapping[str, object], prefix: str) -> tuple[PriceLevel, ...]:
    levels = [_level_from_prefixed_keys(row, prefix, index) for index in range(1, 11)]
    parsed = [level for level in levels if level is not None and level[1] > 0]
    if parsed:
        return _sort_levels(parsed, prefix)
    return _top_of_book_level(row, prefix)


def _level_from_sequence(raw_level: object) -> PriceLevel:
    if not isinstance(raw_level, Sequence) or isinstance(raw_level, str):
        raise ValueError(f"Invalid LOB level {raw_level!r}; expected [price, size]")
    if len(raw_level) < 2:
        raise ValueError(f"Invalid LOB level {raw_level!r}; expected [price, size]")
    return float(raw_level[0]), float(raw_level[1])


def _level_from_prefixed_keys(
    row: Mapping[str, object],
    prefix: str,
    index: int,
) -> PriceLevel | None:
    price = row.get(f"{prefix}_price_{index}")
    size = row.get(f"{prefix}_size_{index}")
    if price is None or size is None:
        return None
    return float(price), float(size)


def _top_of_book_level(
    row: Mapping[str, object],
    prefix: str,
) -> tuple[PriceLevel, ...]:
    price = row.get(prefix)
    size = row.get(f"{prefix}_size", 1.0)
    if price is None:
        return ()
    return ((float(price), float(size)),)


def _sort_levels(levels: list[PriceLevel], prefix: str) -> tuple[PriceLevel, ...]:
    reverse = prefix == "bid"
    return tuple(sorted(levels, key=lambda level: level[0], reverse=reverse))


def _required_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if value is not None and str(value).strip():
        return str(value)
    raise ValueError(f"Invalid LOB row {row!r}; expected non-empty {key!r}")


def _validate_book(
    row: Mapping[str, object],
    bids: tuple[PriceLevel, ...],
    asks: tuple[PriceLevel, ...],
) -> None:
    if bids and asks:
        return
    raise ValueError(f"Invalid LOB row {row!r}; expected bid and ask depth")


def _metadata(row: Mapping[str, object]) -> dict[str, object]:
    excluded = {"timestamp", "symbol", "bids", "asks"}
    return {key: value for key, value in row.items() if key not in excluded}
