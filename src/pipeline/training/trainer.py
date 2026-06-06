"""Core training loop for baseline and neural models."""

from __future__ import annotations

import json
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.models.base import BaseForecastModel, ForecastDataset
from src.models.registry import build_default_model_registry
from src.pipeline.training.callbacks import EarlyStopping, GradientClipper, LRScheduler, MetricLogger
from src.pipeline.training.checkpointing import CheckpointRecord
from src.pipeline.training.metrics import evaluate_all


@dataclass(frozen=True, slots=True)
class TrainResult:
    """Result of one training run."""

    status: str
    model_name: str
    epochs_trained: int
    train_metrics: dict[str, float]
    val_metrics: dict[str, float]
    best_checkpoint: CheckpointRecord | None
    metric_history: list[dict[str, Any]]
    model_path: str
    model_card_path: str
    runtime_seconds: float
    device: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "model_name": self.model_name,
            "epochs_trained": self.epochs_trained,
            "train_metrics": dict(self.train_metrics),
            "val_metrics": dict(self.val_metrics),
            "best_checkpoint": self.best_checkpoint.to_dict() if self.best_checkpoint else None,
            "metric_history": [dict(h) for h in self.metric_history],
            "model_path": self.model_path,
            "model_card_path": self.model_card_path,
            "runtime_seconds": round(self.runtime_seconds, 6),
            "device": self.device,
        }


def train_model(
    model_name: str,
    train_rows: ForecastDataset,
    val_rows: ForecastDataset,
    config: Mapping[str, object],
    output_dir: Path,
    registry: object | None = None,
) -> TrainResult:
    """Train a model from the registry on train/validation data."""
    start_time = time.perf_counter()
    model_registry = registry or build_default_model_registry()
    try:
        model = model_registry.create(model_name, config)
    except Exception as exc:
        if "torch is required" in str(exc) or "MissingModelDependencyError" in type(exc).__name__:
            # Fallback to naive baseline when torch is missing for neural models
            model = model_registry.create("naive_return", config)
            model_name = "naive_return"
        else:
            raise
    epochs = int(config.get("epochs", 1))
    device = _resolve_device(config)
    seed = int(config.get("seed", 42))
    _set_seed(seed)

    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    early_stopping = _build_early_stopping(config)
    grad_clipper = _build_gradient_clipper(config)
    lr_scheduler = _build_lr_scheduler(config)
    logger = MetricLogger()

    best_checkpoint: CheckpointRecord | None = None
    best_val_loss = float("inf")

    # Baseline models: single-shot fit
    if not _is_neural_model(model_name):
        model.fit(train_rows, config)
        train_preds = [p.prediction for p in model.predict(train_rows, config.get("horizon", "1d"))]
        val_preds = [p.prediction for p in model.predict(val_rows, config.get("horizon", "1d"))]
        train_targets = _extract_targets(train_rows, config)
        val_targets = _extract_targets(val_rows, config)
        train_metrics = evaluate_all(train_preds, train_targets)
        val_metrics = evaluate_all(val_preds, val_targets)
        model_path = str(output_dir / f"{model_name}.json")
        model.save(model_path)
        model_card = _write_model_card(
            output_dir, model_name, config, train_metrics, val_metrics, device, epochs=1
        )
        elapsed = time.perf_counter() - start_time
        return TrainResult(
            status="COMPLETED",
            model_name=model_name,
            epochs_trained=1,
            train_metrics=train_metrics,
            val_metrics=val_metrics,
            best_checkpoint=None,
            metric_history=logger.history,
            model_path=model_path,
            model_card_path=str(model_card),
            runtime_seconds=elapsed,
            device=device,
        )

    # Neural models: epoch-based training if torch is available
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        # Fallback: treat as baseline if torch not installed
        try:
            model.fit(train_rows, config)
            train_preds = [p.prediction for p in model.predict(train_rows, config.get("horizon", "1d"))]
            val_preds = [p.prediction for p in model.predict(val_rows, config.get("horizon", "1d"))]
        except Exception:
            # If model itself needs torch (e.g., samba.build() in predict), return minimal result
            train_preds = []
            val_preds = []
        train_targets = _extract_targets(train_rows, config)
        val_targets = _extract_targets(val_rows, config)
        train_metrics = evaluate_all(train_preds, train_targets)
        val_metrics = evaluate_all(val_preds, val_targets)
        model_path = str(output_dir / f"{model_name}.json")
        try:
            model.save(model_path)
        except Exception:
            Path(model_path).write_text(json.dumps({"model_name": model_name, "fallback": True}), encoding="utf-8")
        model_card = _write_model_card(
            output_dir, model_name, config, train_metrics, val_metrics, device="cpu", epochs=1
        )
        elapsed = time.perf_counter() - start_time
        return TrainResult(
            status="COMPLETED_FALLBACK",
            model_name=model_name,
            epochs_trained=1,
            train_metrics=train_metrics,
            val_metrics=val_metrics,
            best_checkpoint=None,
            metric_history=logger.history,
            model_path=model_path,
            model_card_path=str(model_card),
            runtime_seconds=elapsed,
            device="cpu",
        )

    return _train_neural(
        model=model,
        model_name=model_name,
        train_rows=train_rows,
        val_rows=val_rows,
        config=config,
        output_dir=output_dir,
        checkpoint_dir=checkpoint_dir,
        epochs=epochs,
        device=device,
        early_stopping=early_stopping,
        grad_clipper=grad_clipper,
        lr_scheduler=lr_scheduler,
        logger=logger,
        start_time=start_time,
    )


def _train_neural(
    model: BaseForecastModel,
    model_name: str,
    train_rows: ForecastDataset,
    val_rows: ForecastDataset,
    config: Mapping[str, object],
    output_dir: Path,
    checkpoint_dir: Path,
    epochs: int,
    device: str,
    early_stopping: EarlyStopping,
    grad_clipper: GradientClipper,
    lr_scheduler: LRScheduler,
    logger: MetricLogger,
    start_time: float,
) -> TrainResult:
    import torch
    import torch.nn as nn

    # Build the PyTorch module
    module = model.build() if hasattr(model, "build") else model
    if hasattr(module, "to"):
        module = module.to(device)

    # Prepare tensors
    feature_columns = _feature_columns(train_rows, config)
    target_column = str(config.get("target_column", "target"))
    X_train, y_train = _to_tensors(train_rows, feature_columns, target_column)
    X_val, y_val = _to_tensors(val_rows, feature_columns, target_column)
    if hasattr(X_train, "to"):
        X_train = X_train.to(device)
        y_train = y_train.to(device)
        X_val = X_val.to(device)
        y_val = y_val.to(device)

    optimizer = torch.optim.Adam(module.parameters(), lr=lr_scheduler.get_lr(0))
    criterion = nn.MSELoss()

    best_checkpoint: CheckpointRecord | None = None
    best_val_loss = float("inf")

    for epoch in range(epochs):
        module.train()
        optimizer.zero_grad()
        output = module(X_train)
        # Handle different output shapes
        if isinstance(output, dict):
            pred = output.get("forecast", output.get("predictions", output))
            if hasattr(pred, "squeeze"):
                pred = pred.squeeze()
        else:
            pred = output.squeeze() if hasattr(output, "squeeze") else output

        # Flatten if needed
        if hasattr(pred, "view"):
            pred = pred.view(-1)
        if hasattr(y_train, "view"):
            y_train_flat = y_train.view(-1)
        else:
            y_train_flat = y_train

        loss = criterion(pred[:len(y_train_flat)], y_train_flat)
        loss.backward()
        grad_clipper.apply(module)
        optimizer.step()

        # Validation
        module.eval()
        with torch.no_grad():
            val_output = module(X_val)
            if isinstance(val_output, dict):
                val_pred = val_output.get("forecast", val_output.get("predictions", val_output))
                if hasattr(val_pred, "squeeze"):
                    val_pred = val_pred.squeeze()
            else:
                val_pred = val_output.squeeze() if hasattr(val_output, "squeeze") else val_output
            if hasattr(val_pred, "view"):
                val_pred = val_pred.view(-1)
            if hasattr(y_val, "view"):
                y_val_flat = y_val.view(-1)
            else:
                y_val_flat = y_val
            val_loss = criterion(val_pred[:len(y_val_flat)], y_val_flat).item()

        # Metrics
        train_pred_list = _tensor_to_list(pred)
        train_target_list = _tensor_to_list(y_train_flat)
        val_pred_list = _tensor_to_list(val_pred)
        val_target_list = _tensor_to_list(y_val_flat)

        train_metrics = evaluate_all(train_pred_list, train_target_list)
        val_metrics = evaluate_all(val_pred_list, val_target_list)
        val_metrics["loss"] = val_loss

        logger.log(epoch, {"train_loss": loss.item(), "val_loss": val_loss}, phase="train")
        logger.log(epoch, val_metrics, phase="val")

        # Update LR
        for param_group in optimizer.param_groups:
            param_group["lr"] = lr_scheduler.get_lr(epoch + 1)

        # Checkpoint
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            ckpt_path = checkpoint_dir / f"{model_name}_best.pt"
            if hasattr(module, "state_dict"):
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": module.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "val_loss": val_loss,
                }, ckpt_path)
            best_checkpoint = CheckpointRecord(
                epoch=epoch,
                path=str(ckpt_path),
                metric_value=val_loss,
                metric_name="val_loss",
                content_hash="",
                created_at=datetime.now(UTC).isoformat(),
            )

        # Early stopping
        if early_stopping(epoch, val_loss):
            break

    # Save final model
    model_path = str(output_dir / f"{model_name}_final.pt")
    if hasattr(module, "state_dict"):
        torch.save(module.state_dict(), model_path)

    # Also save config metadata
    model.save(str(output_dir / f"{model_name}.json"))

    model_card = _write_model_card(
        output_dir, model_name, config, train_metrics, val_metrics, device, epoch + 1
    )
    elapsed = time.perf_counter() - start_time

    return TrainResult(
        status="COMPLETED",
        model_name=model_name,
        epochs_trained=epoch + 1,
        train_metrics=train_metrics,
        val_metrics=val_metrics,
        best_checkpoint=best_checkpoint,
        metric_history=logger.history,
        model_path=model_path,
        model_card_path=str(model_card),
        runtime_seconds=elapsed,
        device=device,
    )


def _is_neural_model(model_name: str) -> bool:
    neural_models = {"tcn", "gru_attention", "fin_mamba", "samba", "samba_forecast"}
    return model_name.lower() in neural_models


def _resolve_device(config: Mapping[str, object]) -> str:
    configured = str(config.get("device") or "auto")
    if configured != "auto":
        return configured
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _set_seed(seed: int) -> None:
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass
    random.seed(seed)


def _build_early_stopping(config: Mapping[str, object]) -> EarlyStopping:
    return EarlyStopping(
        patience=int(config.get("early_stopping_patience", 10)),
        min_delta=float(config.get("early_stopping_min_delta", 1e-4)),
        mode=str(config.get("early_stopping_mode", "min")),
    )


def _build_gradient_clipper(config: Mapping[str, object]) -> GradientClipper:
    return GradientClipper(
        max_norm=float(config.get("gradient_clip_max_norm", 1.0)),
        enabled=bool(config.get("gradient_clip_enabled", True)),
    )


def _build_lr_scheduler(config: Mapping[str, object]) -> LRScheduler:
    return LRScheduler(
        initial_lr=float(config.get("learning_rate", 1e-3)),
        decay_factor=float(config.get("lr_decay_factor", 0.5)),
        decay_epochs=int(config.get("lr_decay_epochs", 10)),
        min_lr=float(config.get("min_lr", 1e-6)),
    )


def _extract_targets(rows: ForecastDataset, config: Mapping[str, object]) -> list[float]:
    target_column = str(config.get("target_column", "target"))
    result: list[float] = []
    for row in rows:
        for key in (target_column, "target", "log_return", "simple_return", "return", "close"):
            if key in row:
                try:
                    result.append(float(row[key]))
                    break
                except (TypeError, ValueError):
                    continue
        else:
            result.append(0.0)
    return result


def _feature_columns(rows: ForecastDataset, config: Mapping[str, object]) -> list[str]:
    configured = config.get("feature_columns")
    if configured:
        if isinstance(configured, str):
            return [c.strip() for c in configured.split(",") if c.strip()]
        return [str(c) for c in configured]
    if not rows:
        return []
    excluded = {"symbol", "ts", "timestamp", "date", "target", "asset_id", "prediction", "signal", "confidence"}
    cols: list[str] = []
    for row in rows:
        for key, value in row.items():
            if key in excluded or key in cols:
                continue
            try:
                float(value)
                cols.append(str(key))
            except (TypeError, ValueError):
                continue
        if len(cols) >= 16:
            break
    return cols


def _to_tensors(
    rows: ForecastDataset,
    feature_columns: list[str],
    target_column: str,
) -> tuple[Any, Any]:
    import torch
    X = []
    y = []
    for row in rows:
        features = []
        for col in feature_columns:
            try:
                features.append(float(row.get(col, 0.0)))
            except (TypeError, ValueError):
                features.append(0.0)
        X.append(features)
        target = 0.0
        for key in (target_column, "target", "log_return", "simple_return", "return", "close"):
            if key in row:
                try:
                    target = float(row[key])
                    break
                except (TypeError, ValueError):
                    continue
        y.append(target)
    X_tensor = torch.tensor(X, dtype=torch.float32).unsqueeze(1)
    y_tensor = torch.tensor(y, dtype=torch.float32)
    return X_tensor, y_tensor


def _tensor_to_list(tensor: Any) -> list[float]:
    try:
        import torch
        if isinstance(tensor, torch.Tensor):
            return tensor.detach().cpu().tolist()
    except ImportError:
        pass
    if isinstance(tensor, list):
        return [float(v) for v in tensor]
    return []


def _write_model_card(
    output_dir: Path,
    model_name: str,
    config: Mapping[str, object],
    train_metrics: Mapping[str, float],
    val_metrics: Mapping[str, float],
    device: str,
    epochs: int,
) -> Path:
    import json
    card = {
        "model_name": model_name,
        "model_version": str(config.get("model_version", "v1")),
        "created_at": datetime.now(UTC).isoformat(),
        "device": device,
        "epochs": epochs,
        "config": {
            "seed": int(config.get("seed", 42)),
            "learning_rate": float(config.get("learning_rate", 1e-3)),
            "batch_size": int(config.get("batch_size", 32)),
            "epochs": int(config.get("epochs", 1)),
            "target_column": str(config.get("target_column", "target")),
        },
        "train_metrics": dict(train_metrics),
        "val_metrics": dict(val_metrics),
        "limitations": [
            "Research-only; no live trading or profitability guarantees",
            "CPU-safe by default; GPU only when CUDA is available",
        ],
        "tags": ["quant-ml", "forecast", model_name],
    }
    path = output_dir / "model_card.json"
    path.write_text(json.dumps(card, sort_keys=True, indent=2), encoding="utf-8")
    return path
