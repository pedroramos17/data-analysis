"""Corporate action adjustment helpers."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """Split/dividend-style adjustment event."""

    symbol: str
    effective_ts: datetime
    price_factor: float
    known_at: datetime


def load_corporate_actions(config: Mapping[str, object]) -> list[CorporateAction]:
    """Load corporate action rows from inline config or a local CSV/JSON file."""
    rows = config.get("corporate_actions")
    if isinstance(rows, Sequence) and not isinstance(rows, str | bytes):
        return [_action_from_row(dict(row)) for row in rows if isinstance(row, Mapping)]
    path = str(config.get("corporate_actions_path") or "")
    if not path:
        return []
    return [_action_from_row(row) for row in _read_rows(Path(path))]


def apply_corporate_actions(
    rows: Sequence[Mapping[str, object]],
    actions: Sequence[CorporateAction],
    *,
    as_of: str = "2999-12-31T00:00:00+00:00",
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Apply known historical price factors deterministically."""
    as_of_ts = _timestamp(as_of)
    usable = [action for action in actions if action.known_at <= as_of_ts]
    output: list[dict[str, object]] = []
    adjusted_rows = 0
    for row in rows:
        item = dict(row)
        factor = _factor_for_row(item, usable)
        if factor != 1.0:
            for column in ("open", "high", "low", "close"):
                if item.get(column) is not None:
                    item[column] = round(float(item[column]) * factor, 10)
            item["corporate_action_adjusted"] = True
            item["corporate_action_factor"] = factor
            adjusted_rows += 1
        else:
            item["corporate_action_adjusted"] = bool(item.get("corporate_action_adjusted", False))
            item["corporate_action_factor"] = float(item.get("corporate_action_factor", 1.0))
        output.append(item)
    return output, {
        "actions_loaded": len(actions),
        "actions_applied": len(usable),
        "adjusted_rows": adjusted_rows,
        "as_of": as_of_ts.isoformat(),
    }


def _factor_for_row(row: Mapping[str, object], actions: Sequence[CorporateAction]) -> float:
    symbol = str(row.get("symbol") or "").upper()
    ts = _timestamp(row.get("ts"))
    factor = 1.0
    for action in actions:
        if action.symbol == symbol and ts < action.effective_ts:
            factor *= action.price_factor
    return round(factor, 12)


def _action_from_row(row: Mapping[str, object]) -> CorporateAction:
    effective = _timestamp(row.get("effective_ts") or row.get("ex_date") or row.get("date"))
    known_at = _timestamp(row.get("known_at") or row.get("announced_at") or effective)
    factor = float(row.get("price_factor") or row.get("split_factor") or 1.0)
    return CorporateAction(str(row.get("symbol") or "").upper(), effective, factor, known_at)


def _read_rows(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        return [dict(row) for row in loaded if isinstance(row, Mapping)]
    if isinstance(loaded, Mapping) and isinstance(loaded.get("actions"), list):
        return [dict(row) for row in loaded["actions"] if isinstance(row, Mapping)]
    raise ValueError(f"Invalid corporate action file {path}; expected CSV or JSON rows")


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
