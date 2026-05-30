"""Dataset loading helpers for the Mamba smoke experiment."""

from pathlib import Path
import json


def load_dataset(dataset_path: str) -> dict[str, object]:
    """Load a small sequence dataset or return a synthetic fallback.

    Example:
        `dataset = load_dataset("exports/local_simple/model_dataset.npz")`
    """
    path = Path(dataset_path)
    if not path.exists():
        return _synthetic_dataset()
    if path.suffix == ".npz":
        return _load_npz(path)
    if path.suffix == ".json":
        return _load_json(path)
    if path.suffix == ".parquet":
        return _load_parquet(path)
    if path.suffix == ".pt":
        return _load_pt(path)
    message = f"Invalid dataset path {dataset_path!r}; expected npz/json/parquet/pt"
    raise ValueError(message)


def _load_npz(path: Path) -> dict[str, object]:
    import numpy

    data = numpy.load(path)
    return {"samples": data["samples"], "targets": data["targets"]}


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {"metadata": payload, **_synthetic_dataset()}


def _load_parquet(path: Path) -> dict[str, object]:
    try:
        import pyarrow.parquet
    except ImportError:
        return _synthetic_dataset()
    rows = pyarrow.parquet.read_table(path).to_pylist()
    return {"rows": rows, **_synthetic_dataset()}


def _load_pt(path: Path) -> dict[str, object]:
    try:
        import torch
    except ImportError:
        return _synthetic_dataset()
    payload = torch.load(path, map_location="cpu")
    return {"samples": payload["samples"], "targets": payload["targets"]}


def _synthetic_dataset() -> dict[str, object]:
    import numpy

    samples = numpy.zeros((8, 4, 3), dtype="float32")
    targets = numpy.zeros((8, 3), dtype="float32")
    return {"samples": samples, "targets": targets}
