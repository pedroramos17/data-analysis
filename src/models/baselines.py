"""CPU-first baseline forecast models without mandatory heavy dependencies."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from src.models.base import (
    BaseForecastModel,
    ForecastDataset,
    ForecastPrediction,
    MissingModelDependencyError,
    load_json_payload,
    numeric_value,
    row_asset_id,
    row_symbol,
    row_timestamp,
    save_json_payload,
)


@dataclass(slots=True)
class NaiveReturnBaseline(BaseForecastModel):
    """Predict each asset's latest observed return."""

    model_name: str = "naive_return_baseline"
    model_version: str = "v1"
    default_return: float = 0.0
    last_return_by_symbol: dict[str, float] = field(default_factory=dict)

    def fit(self, dataset: ForecastDataset, config: Mapping[str, object]) -> Self:
        """Store the most recent return per symbol."""
        target_column = str(config.get("target_column", "log_return"))
        for row in dataset:
            symbol = row_symbol(row)
            self.last_return_by_symbol[symbol] = _target_value(row, target_column)
        if self.last_return_by_symbol:
            values = list(self.last_return_by_symbol.values())
            self.default_return = sum(values) / len(values)
        return self

    def predict(
        self,
        dataset: ForecastDataset,
        horizon: int | str,
    ) -> list[ForecastPrediction]:
        """Predict the last known return for each row symbol."""
        return [self._prediction(row, horizon) for row in dataset]

    def explain(
        self,
        dataset: ForecastDataset,
        predictions: Sequence[ForecastPrediction],
    ) -> dict[str, object]:
        """Explain the naive baseline behavior."""
        return {
            "model": self.model_name,
            "method": "last_observed_return_by_symbol",
            "row_count": len(dataset),
            "prediction_count": len(predictions),
        }

    def save(self, path: str | Path) -> Path:
        """Save baseline state as JSON."""
        return save_json_payload(path, self.metadata())

    @classmethod
    def load(cls, path: str | Path) -> Self:
        """Load baseline state from JSON."""
        payload = load_json_payload(path)
        return cls(
            model_name=str(payload.get("model_name", "naive_return_baseline")),
            model_version=str(payload.get("model_version", "v1")),
            default_return=float(payload.get("default_return", 0.0)),
            last_return_by_symbol={
                str(key): float(value)
                for key, value in dict(payload.get("last_return_by_symbol", {})).items()
            },
        )

    def metadata(self) -> dict[str, object]:
        """Return registry metadata."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": "baseline",
            "requires_gpu": False,
            "default_return": self.default_return,
            "last_return_by_symbol": dict(self.last_return_by_symbol),
        }

    def _prediction(
        self,
        row: Mapping[str, object],
        horizon: int | str,
    ) -> ForecastPrediction:
        symbol = row_symbol(row)
        value = self.last_return_by_symbol.get(symbol, self.default_return)
        return ForecastPrediction(
            symbol=symbol,
            ts=row_timestamp(row),
            horizon=str(horizon),
            prediction=value,
            signal=value,
            confidence=0.5,
            model_name=self.model_name,
            model_version=self.model_version,
            explanation_json={"baseline": "last_return"},
            asset_id=row_asset_id(row),
        )


@dataclass(slots=True)
class RidgeReturnBaseline(BaseForecastModel):
    """Pure-Python ridge regression baseline for small CPU batches."""

    model_name: str = "ridge_return_baseline"
    model_version: str = "v1"
    alpha: float = 1.0
    feature_columns: list[str] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)

    def fit(self, dataset: ForecastDataset, config: Mapping[str, object]) -> Self:
        """Fit ridge weights using normal equations and Gaussian elimination."""
        self.alpha = float(config.get("alpha", self.alpha))
        self.feature_columns = _feature_columns(dataset, config)
        target_column = str(config.get("target_column", "target"))
        matrix = [[1.0, *_features(row, self.feature_columns)] for row in dataset]
        targets = [_target_value(row, target_column) for row in dataset]
        self.weights = _ridge_weights(matrix, targets, self.alpha)
        return self

    def predict(
        self,
        dataset: ForecastDataset,
        horizon: int | str,
    ) -> list[ForecastPrediction]:
        """Predict with learned ridge weights."""
        return [self._prediction(row, horizon) for row in dataset]

    def explain(
        self,
        dataset: ForecastDataset,
        predictions: Sequence[ForecastPrediction],
    ) -> dict[str, object]:
        """Return coefficient explanation metadata."""
        return {
            "model": self.model_name,
            "feature_columns": list(self.feature_columns),
            "weights": list(self.weights),
            "row_count": len(dataset),
            "prediction_count": len(predictions),
        }

    def save(self, path: str | Path) -> Path:
        """Save ridge state as JSON."""
        return save_json_payload(path, self.metadata())

    @classmethod
    def load(cls, path: str | Path) -> Self:
        """Load ridge state from JSON."""
        payload = load_json_payload(path)
        return cls(
            model_name=str(payload.get("model_name", "ridge_return_baseline")),
            model_version=str(payload.get("model_version", "v1")),
            alpha=float(payload.get("alpha", 1.0)),
            feature_columns=[str(item) for item in payload.get("feature_columns", [])],
            weights=[float(item) for item in payload.get("weights", [])],
        )

    def metadata(self) -> dict[str, object]:
        """Return registry metadata."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": "baseline",
            "requires_gpu": False,
            "alpha": self.alpha,
            "feature_columns": list(self.feature_columns),
            "weights": list(self.weights),
        }

    def _prediction(
        self,
        row: Mapping[str, object],
        horizon: int | str,
    ) -> ForecastPrediction:
        values = [1.0, *_features(row, self.feature_columns)]
        value = sum(weight * feature for weight, feature in zip(self.weights, values))
        return ForecastPrediction(
            symbol=row_symbol(row),
            ts=row_timestamp(row),
            horizon=str(horizon),
            prediction=value,
            signal=value,
            confidence=None,
            model_name=self.model_name,
            model_version=self.model_version,
            explanation_json={"feature_columns": list(self.feature_columns)},
            asset_id=row_asset_id(row),
        )


@dataclass(slots=True)
class OptionalBoostedBaseline(BaseForecastModel):
    """LightGBM/XGBoost baseline loaded only when optional dependencies exist."""

    backend: str
    model_name: str = "boosted_return_baseline"
    model_version: str = "v1"
    estimator: object | None = None
    feature_columns: list[str] = field(default_factory=list)

    def fit(self, dataset: ForecastDataset, config: Mapping[str, object]) -> Self:
        """Fit LightGBM or XGBoost when the selected backend is installed."""
        self.feature_columns = _feature_columns(dataset, config)
        features = [_features(row, self.feature_columns) for row in dataset]
        target_column = str(config.get("target_column", "target"))
        targets = [_target_value(row, target_column) for row in dataset]
        self.estimator = _fit_boosted(self.backend, features, targets)
        return self

    def predict(
        self,
        dataset: ForecastDataset,
        horizon: int | str,
    ) -> list[ForecastPrediction]:
        """Predict with the optional boosted estimator."""
        if self.estimator is None:
            raise MissingModelDependencyError(
                f"{self.backend} estimator is not fitted; expected fit() first"
            )
        rows = [_features(row, self.feature_columns) for row in dataset]
        values = [float(value) for value in self.estimator.predict(rows)]
        return [
            ForecastPrediction(
                symbol=row_symbol(row),
                ts=row_timestamp(row),
                horizon=str(horizon),
                prediction=value,
                signal=value,
                model_name=self.model_name,
                model_version=self.model_version,
                asset_id=row_asset_id(row),
            )
            for row, value in zip(dataset, values, strict=False)
        ]

    def explain(
        self,
        dataset: ForecastDataset,
        predictions: Sequence[ForecastPrediction],
    ) -> dict[str, object]:
        """Return optional boosted model metadata."""
        return {
            "backend": self.backend,
            "feature_columns": list(self.feature_columns),
            "prediction_count": len(predictions),
        }

    def save(self, path: str | Path) -> Path:
        """Save metadata only; estimator serialization remains backend-specific."""
        return save_json_payload(path, self.metadata())

    @classmethod
    def load(cls, path: str | Path) -> Self:
        """Load boosted metadata without estimator state."""
        payload = load_json_payload(path)
        return cls(
            backend=str(payload.get("backend", "lightgbm")),
            model_name=str(payload.get("model_name", "boosted_return_baseline")),
            model_version=str(payload.get("model_version", "v1")),
            feature_columns=[str(item) for item in payload.get("feature_columns", [])],
        )

    def metadata(self) -> dict[str, object]:
        """Return registry metadata."""
        return {
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_type": "optional_boosted_baseline",
            "backend": self.backend,
            "requires_gpu": False,
            "feature_columns": list(self.feature_columns),
        }


def _target_value(row: Mapping[str, object], target_column: str) -> float:
    for key in (target_column, "target", "log_return", "simple_return", "return"):
        if key in row:
            return numeric_value(row[key])
    return 0.0


def _feature_columns(
    dataset: ForecastDataset,
    config: Mapping[str, object],
) -> list[str]:
    configured = config.get("feature_columns", [])
    if isinstance(configured, str):
        return [item.strip() for item in configured.split(",") if item.strip()]
    if configured:
        return [str(item) for item in configured]
    first_row = dataset[0] if dataset else {}
    if "features" in first_row:
        return []
    excluded = {"symbol", "ts", "timestamp", "date", "target", "asset_id"}
    return [
        key
        for key, value in first_row.items()
        if key not in excluded and _is_number(value)
    ]


def _features(row: Mapping[str, object], columns: Sequence[str]) -> list[float]:
    values = row.get("features")
    if isinstance(values, Sequence) and not isinstance(values, str):
        return [numeric_value(value) for value in values]
    return [numeric_value(row.get(column)) for column in columns]


def _ridge_weights(
    matrix: Sequence[Sequence[float]],
    targets: Sequence[float],
    alpha: float,
) -> list[float]:
    if not matrix:
        return [0.0]
    width = len(matrix[0])
    lhs = [[0.0 for _column in range(width)] for _row in range(width)]
    rhs = [0.0 for _row in range(width)]
    for row, target in zip(matrix, targets, strict=False):
        for i in range(width):
            rhs[i] += row[i] * target
            for j in range(width):
                lhs[i][j] += row[i] * row[j]
    for index in range(1, width):
        lhs[index][index] += alpha
    return _solve_linear_system(lhs, rhs)


def _solve_linear_system(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    size = len(rhs)
    augmented = [row[:] + [rhs[index]] for index, row in enumerate(matrix)]
    for pivot_index in range(size):
        pivot = max(
            range(pivot_index, size),
            key=lambda row: abs(augmented[row][pivot_index]),
        )
        augmented[pivot_index], augmented[pivot] = (
            augmented[pivot],
            augmented[pivot_index],
        )
        divisor = augmented[pivot_index][pivot_index]
        if abs(divisor) < 1e-12:
            return [0.0 for _item in range(size)]
        for column in range(pivot_index, size + 1):
            augmented[pivot_index][column] /= divisor
        for row in range(size):
            if row == pivot_index:
                continue
            factor = augmented[row][pivot_index]
            for column in range(pivot_index, size + 1):
                augmented[row][column] -= factor * augmented[pivot_index][column]
    return [augmented[row][size] for row in range(size)]


def _fit_boosted(
    backend: str,
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
) -> object:
    if backend == "lightgbm":
        try:
            from lightgbm import LGBMRegressor
        except ImportError as exc:
            raise MissingModelDependencyError(
                "lightgbm is required for LightGBM baseline; expected optional "
                "dependency"
            ) from exc
        return LGBMRegressor(n_estimators=25).fit(features, targets)
    if backend == "xgboost":
        try:
            from xgboost import XGBRegressor
        except ImportError as exc:
            raise MissingModelDependencyError(
                "xgboost is required for XGBoost baseline; expected optional "
                "dependency"
            ) from exc
        return XGBRegressor(n_estimators=25, objective="reg:squarederror").fit(
            features,
            targets,
        )
    raise ValueError(f"Invalid boosted backend {backend!r}; expected lightgbm/xgboost")


def _is_number(value: object) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
