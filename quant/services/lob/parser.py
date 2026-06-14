"""LOB record parsing for local JSON and JSONL files."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

PriceLevel = tuple[float, float]


@dataclass(frozen=True, slots=True)
class LOBSnapshot:
    """Normalized one-timestamp limit-order-book snapshot.

    Example:
        `LOBSnapshot("t0", "BTC", [(99.0, 1.0)], [(101.0, 1.0)], "crypto")`
    """

    timestamp: str
    symbol: str
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]
    venue_type: str
    metadata: dict[str, object] = field(default_factory=dict)


def parse_lob_jsonl(path: str, venue_type: str = "generic") -> list[LOBSnapshot]:
    """Parse a local JSONL file into normalized LOB snapshots.

    Example:
        `parse_lob_jsonl("data/books.jsonl", venue_type="crypto")`
    """
    rows = _read_jsonl(path)
    from quant.services.lob.normalizer import normalize_lob_rows

    return normalize_lob_rows(rows, venue_type=venue_type)


def parse_lob_records(
    rows: Iterable[Mapping[str, object]],
    venue_type: str = "generic",
) -> list[LOBSnapshot]:
    """Normalize already-loaded LOB records.

    Example:
        `parse_lob_records([{"timestamp": "t0", "bids": [], "asks": []}])`
    """
    from quant.services.lob.normalizer import normalize_lob_rows

    return normalize_lob_rows(rows, venue_type=venue_type)


def _read_jsonl(path: str) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    for line_number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if line.strip():
            rows.append(_parse_json_line(path, line_number, line))
    return rows


def _parse_json_line(path: str, line_number: int, line: str) -> Mapping[str, object]:
    parsed = json.loads(line)
    if isinstance(parsed, dict):
        return parsed
    raise ValueError(
        f"Invalid LOB row {(path, line_number, parsed)!r}; expected JSON object"
    )
