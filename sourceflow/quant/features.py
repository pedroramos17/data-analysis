"""Feature-matrix helpers for quant reasoning modules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping


@dataclass(frozen=True)
class FeatureMatrix:
    """Small feature matrix accepted by local regime detectors."""

    rows: tuple[Mapping[str, Decimal], ...]
    feature_names: tuple[str, ...]
    index: tuple[object, ...] = ()

    def latest(self) -> Mapping[str, Decimal]:
        return self.rows[-1] if self.rows else {}


def build_feature_matrix(rows: Iterable[Mapping[str, object]], *, feature_names: Iterable[str] | None = None) -> FeatureMatrix:
    """Normalize row-like mappings into Decimal feature rows."""
    raw_rows = list(rows)
    names = tuple(feature_names or sorted({key for row in raw_rows for key in row if key != "index"}))
    normalized = []
    index = []
    for row in raw_rows:
        normalized.append({name: Decimal(str(row.get(name, 0) or 0)) for name in names})
        index.append(row.get("index", len(index)))
    return FeatureMatrix(rows=tuple(normalized), feature_names=names, index=tuple(index))


def rolling_change(matrix: FeatureMatrix, feature: str) -> Decimal:
    """Return latest minus previous value for a feature."""
    if len(matrix.rows) < 2:
        return Decimal("0")
    return matrix.rows[-1].get(feature, Decimal("0")) - matrix.rows[-2].get(feature, Decimal("0"))
