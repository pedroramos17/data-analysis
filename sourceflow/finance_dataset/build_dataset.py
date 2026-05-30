"""Build leakage-controlled finance prediction rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from sourceflow.finance_dataset.leakage import assert_no_lookahead


def build_prediction_rows(
    feature_rows: Sequence[Mapping[str, object]],
    target_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Merge feature and target rows after lookahead validation.

    Example:
        `rows = build_prediction_rows(features, targets)`
    """
    assert_no_lookahead(feature_rows)
    targets = {row["timestamp"]: row for row in target_rows}
    return [dict(row) | dict(targets.get(row["timestamp"], {})) for row in feature_rows]
