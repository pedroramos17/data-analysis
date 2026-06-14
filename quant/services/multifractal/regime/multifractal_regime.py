"""Multifractal regime detection for Quant research workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from quant.services.multifractal.defaults import (
    REGIME_DELTA_ALPHA_FLOOR,
    REGIME_MEAN_REVERSION_HURST_THRESHOLD,
    REGIME_MIN_PROBABILITY,
    REGIME_PRIMARY_PROBABILITY,
    REGIME_STRESS_DRAWDOWN_THRESHOLD,
    REGIME_STRESS_LIQUIDITY_THRESHOLD,
    REGIME_TREND_HURST_THRESHOLD,
    REGIME_VOLATILITY_FLOOR,
)
from quant.services.multifractal.regime.change_points import (
    ChangePoint,
    detect_cusum_shifts,
)

CALM = "calm_efficient_regime"
TREND = "persistent_trend_regime"
MEAN_REVERSION = "anti_persistent_mean_reversion_regime"
TURBULENT = "turbulent_multifractal_regime"
STRESS = "crash_liquidity_stress_regime"
INCONCLUSIVE = "inconclusive"
LABELS = (CALM, TREND, MEAN_REVERSION, TURBULENT, STRESS, INCONCLUSIVE)


@dataclass(frozen=True, slots=True)
class MultifractalRegimeLabel:
    """One leakage-safe multifractal regime label.

    Example:
        `label = MultifractalRegimeLabel(1, CALM, 1, {}, {})`
    """

    index: int
    label: str
    training_end_index: int
    probabilities: Mapping[str, float]
    metrics: Mapping[str, float]

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-safe label payload."""
        return {
            "index": self.index,
            "label": self.label,
            "training_end_index": self.training_end_index,
            "probabilities": dict(self.probabilities),
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True, slots=True)
class MultifractalRegimeReport:
    """Regime report with transition and change-point diagnostics.

    Example:
        `payload = report.to_json_dict()`
    """

    labels: tuple[MultifractalRegimeLabel, ...]
    transition_table: Mapping[str, int]
    change_points: tuple[ChangePoint, ...]
    detector_metadata: Mapping[str, object]
    warnings: tuple[str, ...]

    def to_json_dict(self) -> dict[str, object]:
        """Return a JSON-serializable report."""
        return {
            "labels": [label.to_json_dict() for label in self.labels],
            "transition_table": dict(self.transition_table),
            "change_points": [point.to_json_dict() for point in self.change_points],
            "detector_metadata": dict(self.detector_metadata),
            "warnings": list(self.warnings),
        }

    def to_markdown(self) -> str:
        """Return a compact Markdown report."""
        last = self.labels[-1].label if self.labels else INCONCLUSIVE
        return "\n".join(
            [
                "# Multifractal Regime Report",
                "",
                f"- Latest regime: `{last}`",
                f"- Change points: `{len(self.change_points)}`",
                "",
                "These labels are not a trading signal or validity claim.",
            ]
        )


def detect_multifractal_regimes(
    feature_rows: Sequence[Mapping[str, float]],
    window_size: int = 20,
    detector_name: str = "rule_based",
) -> MultifractalRegimeReport:
    """Detect regimes from rolling multifractal feature rows.

    Example:
        `report = detect_multifractal_regimes(rows, window_size=32)`
    """
    _positive_int(window_size, "window_size")
    rows = list(feature_rows)
    labels = tuple(_label_at(rows, index, window_size) for index in range(len(rows)))
    changes = tuple(detect_cusum_shifts(_series(rows, "delta_alpha"), window_size))
    return MultifractalRegimeReport(
        labels=labels,
        transition_table=_transition_table(labels),
        change_points=changes,
        detector_metadata=_metadata(detector_name, rows),
        warnings=_warnings(rows, window_size),
    )


def _label_at(
    rows: Sequence[Mapping[str, float]],
    index: int,
    window_size: int,
) -> MultifractalRegimeLabel:
    current = rows[index]
    history = _past_rows(rows, index, window_size)
    metrics = _metrics(current, history)
    label = _rule_label(metrics)
    return MultifractalRegimeLabel(
        index=index,
        label=label,
        training_end_index=index,
        probabilities=_probabilities(label),
        metrics=metrics,
    )


def _rule_label(metrics: Mapping[str, float]) -> str:
    if metrics["drawdown"] <= REGIME_STRESS_DRAWDOWN_THRESHOLD:
        return STRESS
    if metrics["liquidity"] >= REGIME_STRESS_LIQUIDITY_THRESHOLD:
        return STRESS
    if metrics["delta_alpha"] >= metrics["delta_alpha_high"]:
        return TURBULENT
    if metrics["volatility"] >= metrics["volatility_high"]:
        return TURBULENT
    if metrics["hurst_h2"] >= REGIME_TREND_HURST_THRESHOLD:
        return TREND
    if metrics["hurst_h2"] <= REGIME_MEAN_REVERSION_HURST_THRESHOLD:
        return MEAN_REVERSION
    return CALM


def _metrics(
    current: Mapping[str, float],
    history: Sequence[Mapping[str, float]],
) -> dict[str, float]:
    return {
        "hurst_h2": _value(current, "hurst_h2", 0.5),
        "delta_alpha": _value(current, "delta_alpha", 0.0),
        "asymmetry": _value(current, "spectrum_asymmetry", 0.0),
        "tau_nonlinearity": _value(current, "tau_nonlinearity", 0.0),
        "volatility": _value(current, "realized_volatility", 0.0),
        "drawdown": _value(current, "drawdown", 0.0),
        "liquidity": _value(current, "liquidity_proxy", 0.0),
        "delta_alpha_high": _adaptive_high(
            history,
            "delta_alpha",
            REGIME_DELTA_ALPHA_FLOOR,
        ),
        "volatility_high": _adaptive_high(
            history,
            "realized_volatility",
            REGIME_VOLATILITY_FLOOR,
        ),
    }


def _adaptive_high(
    rows: Sequence[Mapping[str, float]],
    key: str,
    floor: float,
) -> float:
    values = sorted(_value(row, key, 0.0) for row in rows)
    if not values:
        return floor
    index = min(len(values) - 1, int(len(values) * 0.75))
    return max(floor, values[index])


def _probabilities(label: str) -> dict[str, float]:
    remaining = (1.0 - REGIME_PRIMARY_PROBABILITY) / (len(LABELS) - 1)
    return {
        name: REGIME_PRIMARY_PROBABILITY
        if name == label
        else max(REGIME_MIN_PROBABILITY, remaining)
        for name in LABELS
    }


def _transition_table(labels: Sequence[MultifractalRegimeLabel]) -> dict[str, int]:
    table: dict[str, int] = {}
    for previous, current in zip(labels, labels[1:], strict=False):
        key = f"{previous.label}->{current.label}"
        table[key] = table.get(key, 0) + 1
    return table


def _metadata(
    detector_name: str,
    rows: Sequence[Mapping[str, float]],
) -> dict[str, object]:
    return {
        "detector": detector_name,
        "row_count": len(rows),
        "sklearn_optional": _sklearn_state(),
    }


def _sklearn_state() -> str:
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return "missing_optional_dependency"
    return "available_for_kmeans_or_gaussian_mixture"


def _warnings(
    rows: Sequence[Mapping[str, float]],
    window_size: int,
) -> tuple[str, ...]:
    if len(rows) >= window_size:
        return ()
    return (f"Short sample {len(rows)!r}; expected at least {window_size!r} rows",)


def _past_rows(
    rows: Sequence[Mapping[str, float]],
    index: int,
    window_size: int,
) -> Sequence[Mapping[str, float]]:
    start = max(0, index - window_size + 1)
    return rows[start : index + 1]


def _series(rows: Sequence[Mapping[str, float]], key: str) -> list[float]:
    return [_value(row, key, 0.0) for row in rows]


def _value(row: Mapping[str, float], key: str, default: float) -> float:
    value = float(row.get(key, default))
    return value


def _positive_int(value: int, label: str) -> None:
    if isinstance(value, int) and value > 0:
        return
    raise ValueError(f"Invalid {label} {value!r}; expected positive integer")
