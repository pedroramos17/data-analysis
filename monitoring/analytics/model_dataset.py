"""Model dataset tensorization and optional artifact writes."""

from pathlib import Path
import json

from monitoring.compute.array_api import as_float_array


def build_model_dataset_basic(
    values: object,
    window: int = 16,
    horizon: int = 1,
    backend: str = "auto",
    profile: str = "local_cpu_low",
    precision: str = "float32",
    partition: str = "",
) -> dict[str, object]:
    """Build supervised windows for model smoke tests.

    Example:
        `dataset = build_model_dataset_basic([[1], [2], [3]], window=2)`
    """
    array = as_float_array(values, precision)
    _validate_window(array, window, horizon)
    samples = _window_samples(array, window, horizon)
    targets = _window_targets(array, window, horizon)
    return _payload(samples, targets, backend, profile, precision, partition)


def save_model_dataset_artifacts(
    dataset: dict[str, object], output_dir: Path
) -> dict[str, str]:
    """Write model dataset artifacts with optional NPZ and JSON outputs.

    Example:
        `paths = save_model_dataset_artifacts(dataset, Path("exports/local"))`
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {"json": str(_write_dataset_json(dataset, output_dir))}
    npz_path = _write_dataset_npz(dataset, output_dir)
    if npz_path:
        paths["npz"] = str(npz_path)
    pt_path = _write_dataset_pt(dataset, output_dir)
    if pt_path:
        paths["pt"] = str(pt_path)
    return paths


def _window_samples(array: object, window: int, horizon: int) -> object:
    np = _numpy_module()
    count = array.shape[0] - window - horizon + 1
    return np.stack([array[index : index + window] for index in range(count)], axis=0)


def _window_targets(array: object, window: int, horizon: int) -> object:
    np = _numpy_module()
    count = array.shape[0] - window - horizon + 1
    targets = [array[index + window + horizon - 1] for index in range(count)]
    return np.stack(targets, axis=0)


def _payload(
    samples: object,
    targets: object,
    backend: str,
    profile: str,
    precision: str,
    partition: str,
) -> dict[str, object]:
    return {
        "samples": samples,
        "targets": targets,
        "backend": backend,
        "profile": profile,
        "precision": precision,
        "partition": partition,
    }


def _write_dataset_json(dataset: dict[str, object], output_dir: Path) -> Path:
    output_path = output_dir / "model_dataset.json"
    payload = {
        "samples_shape": list(dataset["samples"].shape),
        "targets_shape": list(dataset["targets"].shape),
        "profile": dataset["profile"],
        "precision": dataset["precision"],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def _write_dataset_npz(dataset: dict[str, object], output_dir: Path) -> Path | None:
    np = _numpy_module()
    output_path = output_dir / "model_dataset.npz"
    np.savez(output_path, samples=dataset["samples"], targets=dataset["targets"])
    return output_path


def _write_dataset_pt(dataset: dict[str, object], output_dir: Path) -> Path | None:
    try:
        import torch
    except Exception:
        return None
    output_path = output_dir / "model_dataset.pt"
    torch.save(
        {"samples": dataset["samples"], "targets": dataset["targets"]}, output_path
    )
    return output_path


def _validate_window(array: object, window: int, horizon: int) -> None:
    if window <= 1 or horizon <= 0 or array.shape[0] <= window + horizon:
        shape = getattr(array, "shape", ())
        message = (
            f"Invalid window/horizon {(window, horizon)!r}; "
            f"expected fit within {shape!r}"
        )
        raise ValueError(message)


def _numpy_module() -> object:
    try:
        import numpy
    except ImportError as error:
        message = "Model dataset requires numpy; expected installed package"
        raise RuntimeError(message) from error
    return numpy
