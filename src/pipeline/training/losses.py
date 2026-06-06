"""Loss functions for regression and ranking targets."""

from __future__ import annotations

from collections.abc import Sequence


def mse_loss(predictions: Sequence[float], targets: Sequence[float]) -> float:
    """Mean squared error without PyTorch."""
    n = min(len(predictions), len(targets))
    if n == 0:
        return 0.0
    return sum((p - t) ** 2 for p, t in zip(predictions[:n], targets[:n])) / n


def mae_loss(predictions: Sequence[float], targets: Sequence[float]) -> float:
    """Mean absolute error without PyTorch."""
    n = min(len(predictions), len(targets))
    if n == 0:
        return 0.0
    return sum(abs(p - t) for p, t in zip(predictions[:n], targets[:n])) / n


def huber_loss(predictions: Sequence[float], targets: Sequence[float], delta: float = 1.0) -> float:
    """Huber loss for robust regression."""
    n = min(len(predictions), len(targets))
    if n == 0:
        return 0.0
    total = 0.0
    for p, t in zip(predictions[:n], targets[:n]):
        diff = abs(p - t)
        if diff <= delta:
            total += 0.5 * diff ** 2
        else:
            total += delta * (diff - 0.5 * delta)
    return total / n


def rank_loss(predictions: Sequence[float], targets: Sequence[float]) -> float:
    """Pairwise ranking loss (simplified)."""
    n = min(len(predictions), len(targets))
    if n < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            target_diff = targets[i] - targets[j]
            pred_diff = predictions[i] - predictions[j]
            if target_diff == 0:
                continue
            sign = 1.0 if target_diff > 0 else -1.0
            total += max(0.0, 1.0 - sign * pred_diff)
            count += 1
    return total / max(count, 1)


def directional_loss(predictions: Sequence[float], targets: Sequence[float]) -> float:
    """Penalty for wrong directional predictions."""
    n = min(len(predictions), len(targets))
    if n == 0:
        return 0.0
    total = 0.0
    count = 0
    for i in range(1, n):
        target_dir = 1.0 if targets[i] > targets[i - 1] else -1.0
        pred_dir = 1.0 if predictions[i] > predictions[i - 1] else -1.0
        if target_dir != pred_dir:
            total += 1.0
        count += 1
    return total / max(count, 1)


def combined_loss(
    predictions: Sequence[float],
    targets: Sequence[float],
    *,
    mse_weight: float = 1.0,
    mae_weight: float = 0.5,
    rank_weight: float = 0.1,
    dir_weight: float = 0.1,
) -> dict[str, float]:
    """Return a combined loss dictionary with per-component breakdown."""
    mse = mse_loss(predictions, targets)
    mae = mae_loss(predictions, targets)
    rank = rank_loss(predictions, targets)
    direction = directional_loss(predictions, targets)
    total = mse_weight * mse + mae_weight * mae + rank_weight * rank + dir_weight * direction
    return {
        "loss_total": total,
        "loss_mse": mse,
        "loss_mae": mae,
        "loss_rank": rank,
        "loss_directional": direction,
    }
