"""Tiny NRDE smoke experiment with optional PyTorch."""

from pathlib import Path
import argparse
import json
import time

from load_dataset import load_dataset


def main() -> int:
    """Run the NRDE smoke CLI."""
    config = _load_config(_parse_args().config)
    dataset = load_dataset(str(config.get("dataset_path", "")))
    metrics = _torch_or_fallback_metrics(dataset)
    _write_metrics(config, metrics)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def _load_config(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _torch_or_fallback_metrics(dataset: dict[str, object]) -> dict[str, object]:
    try:
        import torch
    except ImportError:
        return _fallback_metrics(dataset, "numpy_fallback")
    samples = torch.as_tensor(dataset["samples"]).float()
    targets = torch.as_tensor(dataset["targets"]).float()
    prediction = samples.mean(dim=1)
    loss = torch.mean((prediction - targets) ** 2).item()
    return {"loss": loss, "backend": "torch", "samples": int(samples.shape[0])}


def _fallback_metrics(dataset: dict[str, object], backend: str) -> dict[str, object]:
    samples = dataset["samples"]
    targets = dataset["targets"]
    loss = float(((samples.mean(axis=1) - targets) ** 2).mean())
    return {"loss": loss, "backend": backend, "samples": int(samples.shape[0])}


def _write_metrics(config: dict[str, object], metrics: dict[str, object]) -> Path:
    output_dir = Path(str(config.get("output_dir", "exports/experiments/nrde")))
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics["created_at_unix"] = int(time.time())
    output_path = output_dir / "metrics.json"
    output_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    raise SystemExit(main())

