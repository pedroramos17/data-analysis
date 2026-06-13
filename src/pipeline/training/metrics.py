"""Training and evaluation metrics for forecast models."""

from __future__ import annotations

import math
from collections.abc import Sequence

BYTES_PER_KIB = 1024.0
BYTES_PER_MIB = BYTES_PER_KIB * BYTES_PER_KIB
SECONDS_PER_HOUR = 3600.0


def mse(predictions: Sequence[float], targets: Sequence[float]) -> float:
    n = min(len(predictions), len(targets))
    if n == 0:
        return float("nan")
    return sum((p - t) ** 2 for p, t in zip(predictions[:n], targets[:n])) / n


def rmse(predictions: Sequence[float], targets: Sequence[float]) -> float:
    return math.sqrt(mse(predictions, targets))


def mae(predictions: Sequence[float], targets: Sequence[float]) -> float:
    n = min(len(predictions), len(targets))
    if n == 0:
        return float("nan")
    return sum(abs(p - t) for p, t in zip(predictions[:n], targets[:n])) / n


def directional_accuracy(predictions: Sequence[float], targets: Sequence[float]) -> float:
    """Fraction of periods where prediction and target move in the same direction."""
    n = min(len(predictions), len(targets))
    if n < 2:
        return 0.0
    correct = 0
    for i in range(1, n):
        pred_dir = predictions[i] - predictions[i - 1]
        target_dir = targets[i] - targets[i - 1]
        if pred_dir == 0 or target_dir == 0:
            continue
        if (pred_dir > 0) == (target_dir > 0):
            correct += 1
    return correct / (n - 1)


def information_coefficient(predictions: Sequence[float], targets: Sequence[float]) -> float:
    """Pearson correlation between predictions and targets."""
    n = min(len(predictions), len(targets))
    if n < 2:
        return 0.0
    pred_mean = sum(predictions[:n]) / n
    target_mean = sum(targets[:n]) / n
    num = sum((p - pred_mean) * (t - target_mean) for p, t in zip(predictions[:n], targets[:n]))
    pred_var = sum((p - pred_mean) ** 2 for p in predictions[:n])
    target_var = sum((t - target_mean) ** 2 for t in targets[:n])
    denom = math.sqrt(pred_var * target_var)
    if denom < 1e-12:
        return 0.0
    return num / denom


def rank_ic(predictions: Sequence[float], targets: Sequence[float]) -> float:
    """Spearman rank correlation between predictions and targets."""
    n = min(len(predictions), len(targets))
    if n < 2:
        return 0.0
    pred_ranks = _ranks(predictions[:n])
    target_ranks = _ranks(targets[:n])
    return information_coefficient(pred_ranks, target_ranks)


def hit_ratio(predictions: Sequence[float], targets: Sequence[float], threshold: float = 0.0) -> float:
    """Fraction of predictions that have the same sign as the target when |target| > threshold."""
    n = min(len(predictions), len(targets))
    if n == 0:
        return 0.0
    hits = 0
    count = 0
    for p, t in zip(predictions[:n], targets[:n]):
        if abs(t) <= threshold:
            continue
        if (p >= 0) == (t >= 0):
            hits += 1
        count += 1
    return hits / max(count, 1)


def sharpe_like(returns: Sequence[float]) -> float:
    """Sharpe-like ratio from a series of returns (no risk-free rate)."""
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    if std < 1e-12:
        return 0.0
    return mean / std


def max_drawdown(returns: Sequence[float]) -> float:
    """Maximum drawdown from a cumulative return series."""
    if not returns:
        return 0.0
    peak = returns[0]
    max_dd = 0.0
    for r in returns:
        if r > peak:
            peak = r
        dd = (peak - r) / max(abs(peak), 1e-12)
        if dd > max_dd:
            max_dd = dd
    return max_dd


def turnover_proxy(predictions: Sequence[float]) -> float:
    """Average absolute change in predictions as a turnover proxy."""
    n = len(predictions)
    if n < 2:
        return 0.0
    total = sum(abs(predictions[i] - predictions[i - 1]) for i in range(1, n))
    return total / (n - 1)


def latency_per_batch_ms(elapsed_seconds: float, num_batches: int) -> float:
    if num_batches <= 0:
        return 0.0
    return (elapsed_seconds * 1000.0) / num_batches


def samples_per_second(num_samples: int, elapsed_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    return num_samples / elapsed_seconds


def gpu_memory_mb() -> float:
    """Return GPU memory used in MB, or 0 if unavailable."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / BYTES_PER_MIB
    except ImportError:
        pass
    return 0.0


def cpu_memory_mb() -> float:
    """Return current process RSS in MB."""
    try:
        import resource
        return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / BYTES_PER_KIB
    except ImportError:
        return 0.0


def cost_proxy(elapsed_seconds: float, gpu_hourly_cost: float = 0.0) -> float:
    """Estimate cost in USD from elapsed time and hourly GPU rate."""
    hours = elapsed_seconds / SECONDS_PER_HOUR
    return hours * gpu_hourly_cost


def evaluate_all(
    predictions: Sequence[float],
    targets: Sequence[float],
    elapsed_seconds: float = 0.0,
    num_batches: int = 0,
    gpu_hourly_cost: float = 0.0,
) -> dict[str, float]:
    """Compute all metrics at once."""
    metrics: dict[str, float] = {
        "mse": mse(predictions, targets),
        "rmse": rmse(predictions, targets),
        "mae": mae(predictions, targets),
        "directional_accuracy": directional_accuracy(predictions, targets),
        "ic": information_coefficient(predictions, targets),
        "rank_ic": rank_ic(predictions, targets),
        "hit_ratio": hit_ratio(predictions, targets),
        "turnover_proxy": turnover_proxy(predictions),
        "sharpe_like": sharpe_like(predictions),
        "max_drawdown": max_drawdown(predictions),
        "latency_ms_per_batch": latency_per_batch_ms(elapsed_seconds, num_batches),
        "samples_per_sec": samples_per_second(len(predictions), elapsed_seconds),
        "gpu_memory_mb": gpu_memory_mb(),
        "cpu_memory_mb": cpu_memory_mb(),
        "cost_proxy_usd": cost_proxy(elapsed_seconds, gpu_hourly_cost),
    }
    return metrics


def _ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    result = [0.0] * len(values)
    for rank, (idx, _) in enumerate(indexed):
        result[idx] = float(rank)
    return result
