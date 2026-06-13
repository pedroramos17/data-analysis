"""Lightweight signal explanations and alpha diagnostics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from itertools import zip_longest

from src.models.base import ForecastDataset, ForecastPrediction, numeric_value

SIGNAL_EXPLANATION_FIELDS = (
    "model_name",
    "model_version",
    "feature_set_version",
    "top_features",
    "horizon",
    "confidence",
    "uncertainty_proxy",
    "regime_context",
    "risk_context",
    "data_quality_flags",
)

ALPHA_VALIDATION_FIELDS = (
    "ic",
    "rank_ic",
    "hit_ratio",
    "turnover",
    "drawdown",
    "sharpe_like",
    "sortino_like",
    "calmar_like",
    "melao_index_placeholder",
    "correlation_with_existing_signals",
    "regime_conditional_performance",
)

EXCLUDED_FEATURE_COLUMNS = frozenset(
    {
        "asset_id",
        "confidence",
        "date",
        "horizon",
        "ingestion_run_id",
        "model_name",
        "model_version",
        "prediction",
        "signal",
        "source",
        "symbol",
        "timestamp",
        "ts",
    }
)

REGIME_KEYS = (
    "regime",
    "regime_context",
    "volatility_regime",
    "trend_regime",
    "correlation_regime",
    "liquidity_regime",
)
RISK_KEYS = (
    "drawdown",
    "max_drawdown",
    "volatility",
    "realized_volatility",
    "realized_volatility_20",
    "realized_volatility_60",
    "value_at_risk",
    "var",
    "cvar",
    "expected_shortfall",
    "beta",
)


def enrich_prediction_explanations(
    model: object,
    dataset: ForecastDataset,
    predictions: Sequence[ForecastPrediction],
    model_explanation: Mapping[str, object] | None = None,
    *,
    feature_set_version: str = "",
) -> list[ForecastPrediction]:
    """Return predictions with the required non-black-box explanation envelope."""
    model_metadata = _safe_model_metadata(model)
    enriched: list[ForecastPrediction] = []
    for row, prediction in zip_longest(dataset, predictions, fillvalue={}):
        if not isinstance(prediction, ForecastPrediction):
            continue
        explanation = build_signal_explanation(
            prediction,
            row if isinstance(row, Mapping) else {},
            model_explanation or {},
            model_metadata,
            feature_set_version=feature_set_version,
        )
        enriched.append(replace(prediction, explanation_json=explanation))
    return enriched


def build_signal_explanation(
    prediction: ForecastPrediction,
    row: Mapping[str, object] | None = None,
    model_explanation: Mapping[str, object] | None = None,
    model_metadata: Mapping[str, object] | None = None,
    *,
    feature_set_version: str = "",
) -> dict[str, object]:
    """Build the required signal explanation payload for DB/API/Parquet outputs."""
    source = dict(prediction.explanation_json or {})
    active_row = dict(row or {})
    active_model_explanation = dict(model_explanation or {})
    active_model_metadata = dict(model_metadata or {})
    feature_columns = _feature_columns(source, active_model_explanation, active_model_metadata)
    flags = _data_quality_flags(active_row, prediction, feature_columns)
    payload = source | {
        "model_name": prediction.model_name,
        "model_version": prediction.model_version,
        "feature_set_version": str(
            source.get("feature_set_version")
            or feature_set_version
            or active_model_explanation.get("feature_set_version")
            or ""
        ),
        "top_features": _existing_or_top_features(source, active_row, feature_columns),
        "horizon": prediction.horizon,
        "confidence": prediction.confidence,
        "uncertainty_proxy": _uncertainty_proxy(source, prediction),
        "regime_context": _context_payload(source, active_row, REGIME_KEYS),
        "risk_context": _risk_context_payload(source, active_row, prediction),
        "data_quality_flags": _merge_flags(source.get("data_quality_flags"), flags),
    }
    if active_model_explanation:
        payload.setdefault("model_explanation", _json_safe(active_model_explanation))
    return _json_safe_dict(payload)


def ensure_signal_explanation(
    prediction: ForecastPrediction,
    *,
    feature_set_version: str = "",
) -> dict[str, object]:
    """Return a complete explanation for already-created prediction rows."""
    return build_signal_explanation(
        prediction,
        {},
        {},
        {},
        feature_set_version=feature_set_version,
    )


def sequence_prediction_explanation(
    *,
    architecture: str,
    feature_columns: Sequence[str] = (),
    temporal_contribution: object = None,
    feature_saliency: object = None,
    branch_names: Sequence[str] = (),
    branch_contribution: object = None,
    latent_state_summary: Mapping[str, object] | None = None,
    uncertainty_proxy: object = None,
) -> dict[str, object]:
    """Return JSON-safe sequence-model diagnostics for one prediction."""
    saliency_values = _vector_values(feature_saliency)
    return _json_safe_dict(
        {
            "architecture": architecture,
            "feature_columns": [str(value) for value in feature_columns],
            "temporal_contribution_summary": _vector_values(temporal_contribution),
            "feature_saliency_placeholder": _feature_saliency_payload(
                feature_columns,
                saliency_values,
            ),
            "branch_diagnostics": _branch_payload(branch_names, branch_contribution),
            "latent_state_summary": dict(latent_state_summary or {}),
            "uncertainty_proxy": _optional_float(uncertainty_proxy),
        }
    )


def alpha_validation_metrics(
    rows: Sequence[Mapping[str, object]],
    predictions: Sequence[ForecastPrediction],
    *,
    existing_signals: Sequence[float] | None = None,
) -> dict[str, object]:
    """Compute lightweight alpha diagnostics without optional dependencies."""
    signal_by_symbol = {prediction.symbol: float(prediction.signal) for prediction in predictions}
    actuals: list[float] = []
    signals: list[float] = []
    strategy_returns: list[float] = []
    regimes: list[str] = []
    for row in rows:
        symbol = str(row.get("symbol") or "")
        if symbol not in signal_by_symbol:
            continue
        actual = _actual_return(row)
        signal = signal_by_symbol[symbol]
        actuals.append(actual)
        signals.append(signal)
        strategy_returns.append(actual * signal)
        regimes.append(_regime_label(row))
    drawdown = min(_cumulative_drawdowns(strategy_returns), default=0.0)
    total_return = sum(strategy_returns)
    existing = list(existing_signals or [])
    return _json_safe_dict(
        {
            "ic": _correlation(signals, actuals),
            "rank_ic": _correlation(_ranks(signals), _ranks(actuals)),
            "hit_ratio": _hit_ratio(signals, actuals),
            "turnover": _turnover(signals),
            "drawdown": drawdown,
            "sharpe_like": _sharpe_like(strategy_returns),
            "sortino_like": _sortino_like(strategy_returns),
            "calmar_like": total_return / (abs(drawdown) or 1e-12),
            "melao_index_placeholder": {
                "status": "placeholder",
                "reason": "Melao Index remains feature-flagged research metric",
            },
            "correlation_with_existing_signals": (
                _correlation(signals, existing[: len(signals)]) if existing else None
            ),
            "regime_conditional_performance": _regime_performance(
                regimes,
                signals,
                actuals,
                strategy_returns,
            ),
            "observations": len(strategy_returns),
        }
    )


def tensor_item(value: object, index: int) -> object:
    """Return one batch item from a tensor-like object without importing torch."""
    if value is None:
        return None
    shape = getattr(value, "shape", None)
    if shape is not None and len(shape) > 0:
        try:
            return value[index]
        except Exception:
            return value
    return value


def tensor_summary(value: object) -> dict[str, object]:
    """Return a compact JSON-safe summary of a tensor-like object."""
    if value is None:
        return {}
    shape = getattr(value, "shape", None)
    values = _flatten(_as_python(value))
    numeric = [_float_value(item) for item in values]
    numeric = [item for item in numeric if item is not None]
    return {
        "shape": [int(item) for item in shape] if shape is not None else [],
        "mean_abs": _mean([abs(item) for item in numeric]),
        "max_abs": max([abs(item) for item in numeric], default=0.0),
    }


def _safe_model_metadata(model: object) -> dict[str, object]:
    metadata = getattr(model, "metadata", None)
    if not callable(metadata):
        return {}
    try:
        payload = metadata()
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _feature_columns(
    source: Mapping[str, object],
    model_explanation: Mapping[str, object],
    model_metadata: Mapping[str, object],
) -> list[str]:
    for payload in (source, model_explanation, model_metadata):
        configured = payload.get("feature_columns")
        if isinstance(configured, str):
            return [item.strip() for item in configured.split(",") if item.strip()]
        if isinstance(configured, Sequence) and not isinstance(configured, str | bytes):
            return [str(item) for item in configured]
    return []


def _existing_or_top_features(
    source: Mapping[str, object],
    row: Mapping[str, object],
    feature_columns: Sequence[str],
) -> list[dict[str, object]]:
    existing = source.get("top_features")
    if isinstance(existing, Sequence) and not isinstance(existing, str | bytes):
        return [_json_safe_dict(dict(item)) for item in existing if isinstance(item, Mapping)]
    return _top_features(row, feature_columns)


def _top_features(
    row: Mapping[str, object],
    feature_columns: Sequence[str],
    limit: int = 5,
) -> list[dict[str, object]]:
    candidates = list(feature_columns) or [
        str(key) for key in row if str(key) not in EXCLUDED_FEATURE_COLUMNS
    ]
    scored: list[tuple[str, float, float]] = []
    for name in candidates:
        value = _float_value(row.get(name))
        if value is None:
            continue
        scored.append((name, value, abs(value)))
    total = sum(score for _name, _value, score in scored) or 1.0
    return [
        {"name": name, "value": value, "importance_proxy": score / total}
        for name, value, score in sorted(scored, key=lambda item: item[2], reverse=True)[:limit]
    ]


def _uncertainty_proxy(
    source: Mapping[str, object],
    prediction: ForecastPrediction,
) -> float:
    existing = _float_value(source.get("uncertainty_proxy"))
    if existing is not None:
        return max(0.0, existing)
    if prediction.confidence is not None:
        return max(0.0, 1.0 - max(0.0, min(1.0, float(prediction.confidence))))
    return abs(float(prediction.prediction) - float(prediction.signal))


def _context_payload(
    source: Mapping[str, object],
    row: Mapping[str, object],
    keys: Sequence[str],
) -> dict[str, object]:
    for key in keys:
        existing = source.get(key)
        if isinstance(existing, Mapping):
            return _json_safe_dict(existing)
    values = {key: row[key] for key in keys if key in row}
    if values:
        return _json_safe_dict(values)
    return {"source": "not_provided"}


def _risk_context_payload(
    source: Mapping[str, object],
    row: Mapping[str, object],
    prediction: ForecastPrediction,
) -> dict[str, object]:
    existing = source.get("risk_context")
    if isinstance(existing, Mapping):
        return _json_safe_dict(existing)
    values = {key: row[key] for key in RISK_KEYS if key in row}
    values["signal_magnitude"] = abs(float(prediction.signal))
    values["prediction_magnitude"] = abs(float(prediction.prediction))
    return _json_safe_dict(values)


def _data_quality_flags(
    row: Mapping[str, object],
    prediction: ForecastPrediction,
    feature_columns: Sequence[str],
) -> list[str]:
    flags: list[str] = []
    if not prediction.symbol or prediction.symbol == "UNKNOWN":
        flags.append("missing_symbol")
    if not prediction.ts:
        flags.append("missing_timestamp")
    if not math.isfinite(float(prediction.prediction)):
        flags.append("non_finite_prediction")
    if prediction.confidence is not None and prediction.confidence < 0.25:
        flags.append("low_confidence")
    missing_features = [name for name in feature_columns if name not in row]
    if missing_features:
        flags.append("missing_configured_features")
    return flags


def _merge_flags(existing: object, generated: Sequence[str]) -> list[str]:
    flags: list[str] = []
    if isinstance(existing, Sequence) and not isinstance(existing, str | bytes):
        flags.extend(str(item) for item in existing)
    flags.extend(generated)
    return sorted(set(flags))


def _feature_saliency_payload(
    feature_columns: Sequence[str],
    saliency_values: Sequence[float],
) -> list[dict[str, object]]:
    names = [str(value) for value in feature_columns]
    if not names:
        names = [f"feature_{index}" for index in range(len(saliency_values))]
    total = sum(abs(value) for value in saliency_values) or 1.0
    return [
        {
            "name": name,
            "importance_proxy": abs(float(saliency_values[index])) / total,
        }
        for index, name in enumerate(names[: len(saliency_values)])
    ]


def _branch_payload(
    branch_names: Sequence[str],
    branch_contribution: object,
) -> dict[str, object]:
    values = _vector_values(branch_contribution)
    names = [str(name) for name in branch_names]
    weights = {
        names[index] if index < len(names) else f"branch_{index}": values[index]
        for index in range(len(values))
    }
    return {"branch_names": names, "branch_contribution_summary": weights}


def _vector_values(value: object, limit: int = 20) -> list[float]:
    values = _flatten(_as_python(value))
    numeric = [_float_value(item) for item in values]
    return [float(item) for item in numeric if item is not None][:limit]


def _as_python(value: object) -> object:
    current = value
    for method_name in ("detach", "cpu"):
        method = getattr(current, method_name, None)
        if callable(method):
            current = method()
    tolist = getattr(current, "tolist", None)
    if callable(tolist):
        return tolist()
    return current


def _flatten(value: object) -> list[object]:
    if isinstance(value, list | tuple):
        flattened: list[object] = []
        for item in value:
            flattened.extend(_flatten(item))
        return flattened
    if value is None:
        return []
    return [value]


def _actual_return(row: Mapping[str, object]) -> float:
    for key in ("actual_return", "future_return", "target", "log_return", "simple_return"):
        if key in row:
            return numeric_value(row[key])
    return 0.0


def _regime_label(row: Mapping[str, object]) -> str:
    for key in REGIME_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return "all"


def _hit_ratio(signals: Sequence[float], actuals: Sequence[float]) -> float:
    if not signals:
        return 0.0
    hits = [
        _sign(signal) == _sign(actual)
        for signal, actual in zip(signals, actuals, strict=False)
        if _sign(signal) != 0 and _sign(actual) != 0
    ]
    return sum(1 for hit in hits if hit) / len(hits) if hits else 0.0


def _turnover(signals: Sequence[float]) -> float:
    changes = [
        abs(right - left) for left, right in zip(signals, signals[1:], strict=False)
    ]
    return sum(changes) / len(changes) if changes else 0.0


def _sharpe_like(returns: Sequence[float]) -> float:
    return _mean(returns) / (_stddev(returns) or 1e-12)


def _sortino_like(returns: Sequence[float]) -> float:
    downside = [min(value, 0.0) for value in returns]
    return _mean(returns) / (_stddev(downside) or 1e-12)


def _regime_performance(
    regimes: Sequence[str],
    signals: Sequence[float],
    actuals: Sequence[float],
    strategy_returns: Sequence[float],
) -> dict[str, object]:
    grouped: dict[str, dict[str, list[float]]] = {}
    for regime, signal, actual, strategy_return in zip(
        regimes,
        signals,
        actuals,
        strategy_returns,
        strict=False,
    ):
        bucket = grouped.setdefault(regime, {"signals": [], "actuals": [], "returns": []})
        bucket["signals"].append(signal)
        bucket["actuals"].append(actual)
        bucket["returns"].append(strategy_return)
    return {
        regime: {
            "observations": len(values["returns"]),
            "mean_return": _mean(values["returns"]),
            "hit_ratio": _hit_ratio(values["signals"], values["actuals"]),
        }
        for regime, values in grouped.items()
    }


def _ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0 for _item in values]
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        rank = (index + end - 1) / 2.0 + 1.0
        for original_index, _value in indexed[index:end]:
            ranks[original_index] = rank
        index = end
    return ranks


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    pairs = [(float(a), float(b)) for a, b in zip(left, right, strict=False)]
    if len(pairs) < 2:
        return 0.0
    left_values = [item[0] for item in pairs]
    right_values = [item[1] for item in pairs]
    mean_left = _mean(left_values)
    mean_right = _mean(right_values)
    numerator = sum(
        (left_value - mean_left) * (right_value - mean_right)
        for left_value, right_value in pairs
    )
    denominator = _sum_square_scale(left_values, mean_left) * _sum_square_scale(
        right_values,
        mean_right,
    )
    return numerator / denominator if denominator else 0.0


def _sum_square_scale(values: Sequence[float], mean_value: float) -> float:
    return math.sqrt(sum((value - mean_value) ** 2 for value in values))


def _cumulative_drawdowns(returns: Sequence[float]) -> list[float]:
    total = 0.0
    peak = 0.0
    drawdowns: list[float] = []
    for value in returns:
        total += value
        peak = max(peak, total)
        drawdowns.append(total - peak)
    return drawdowns


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean_value = _mean(values)
    return math.sqrt(
        sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sign(value: float) -> int:
    if value > 0.0:
        return 1
    if value < 0.0:
        return -1
    return 0


def _optional_float(value: object) -> float | None:
    parsed = _float_value(value)
    return parsed if parsed is not None else None


def _float_value(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _json_safe_dict(payload: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _json_safe(value) for key, value in payload.items()}


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return _json_safe_dict(value)
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
