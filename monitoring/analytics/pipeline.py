"""Local simple analytics pipeline orchestration."""

from pathlib import Path
import json

from monitoring.analytics.feature_store import (
    build_asset_panel,
    build_feature_store_basic,
)
from monitoring.analytics.graphs import compute_graph_features
from monitoring.analytics.mfdfa import compute_mfdfa_features
from monitoring.analytics.model_dataset import (
    build_model_dataset_basic,
    save_model_dataset_artifacts,
)
from monitoring.analytics.signatures import compute_signature_features
from monitoring.analytics.wavelet import compute_wavelet_features
from monitoring.compute.limits import apply_resource_limits
from monitoring.compute.profiles import get_compute_profile


LOCAL_SIMPLE_TASKS = (
    "build_asset_panel",
    "build_feature_store_basic",
    "wavelet_basic",
    "mfdfa_small",
    "signature_simple",
    "graph_light",
    "build_model_dataset_basic",
)


def run_local_simple_pipeline(
    profile: str,
    output_dir: Path,
    enable_micro_gpu: bool = False,
    max_vram_gb: float | None = None,
    queue: bool = False,
) -> dict[str, object]:
    """Run a bounded local-only analytics pipeline.

    Example:
        `run_local_simple_pipeline("local_cpu_low", Path("exports/local_simple"))`
    """
    compute_profile = get_compute_profile(profile)
    _validate_local_profile(compute_profile.name)
    output_dir.mkdir(parents=True, exist_ok=True)
    limits = apply_resource_limits(_task_config(max_vram_gb), profile)
    values = _sample_values()
    artifacts, warnings = _run_steps(values, output_dir, profile, limits)
    manifest = _manifest(profile, limits, artifacts, warnings, enable_micro_gpu, queue)
    _write_json(output_dir / "local_simple_manifest.json", manifest)
    return manifest


def _run_steps(
    values: object,
    output_dir: Path,
    profile: str,
    limits: dict[str, object],
) -> tuple[dict[str, str], list[str]]:
    artifacts: dict[str, str] = {}
    warnings: list[str] = []
    panel = build_asset_panel(values)
    features = build_feature_store_basic(
        values, int(limits["window"]) // 16, profile=profile
    )
    artifacts["asset_panel"] = str(
        _write_json(output_dir / "asset_panel.json", _shape_payload(panel))
    )
    artifacts["feature_store"] = str(
        _write_feature_store(features, output_dir, warnings)
    )
    artifacts["wavelet"] = str(
        _write_json(
            output_dir / "wavelet_features.json",
            _wavelet_payload(values, limits, profile),
        )
    )
    artifacts["mfdfa"] = str(
        _write_json(
            output_dir / "mfdfa_features.json",
            _mfdfa_payload(values, limits, profile),
        )
    )
    artifacts["signatures"] = str(
        _write_json(
            output_dir / "signature_features.json",
            _signature_payload(values, limits, profile),
        )
    )
    artifacts["graph"] = str(
        _write_json(
            output_dir / "graph_light.json", _graph_payload(values, limits, profile)
        )
    )
    dataset = build_model_dataset_basic(values, window=16, profile=profile)
    artifacts.update(save_model_dataset_artifacts(dataset, output_dir))
    _write_json(output_dir / "warnings.json", {"warnings": warnings})
    return artifacts, warnings


def _write_feature_store(
    features: dict[str, object], output_dir: Path, warnings: list[str]
) -> Path:
    rows = _feature_rows(features)
    parquet_path = output_dir / "feature_store.parquet"
    if _write_parquet_rows(rows, parquet_path):
        return parquet_path
    warnings.append("PyArrow unavailable; wrote feature_store.json instead")
    return _write_json(output_dir / "feature_store.json", {"rows": rows})


def _feature_rows(features: dict[str, object]) -> list[dict[str, object]]:
    returns = features["returns"]
    rolling_mean = features["rolling_mean"]
    rows: list[dict[str, object]] = []
    for index in range(returns.shape[0]):
        rows.append({"row": str(index), "returns": returns[index].tolist()})
    rows.append({"row": "rolling_mean_last", "returns": rolling_mean[-1].tolist()})
    return rows


def _wavelet_payload(
    values: object, limits: dict[str, object], profile: str
) -> dict[str, object]:
    result = compute_wavelet_features(
        values,
        profile=profile,
        batch_size=int(limits["batch_size"]),
        max_vram_gb=float(limits["max_vram_gb"]),
    )
    return {
        "energy_shape": list(result["energy"].shape),
        "entropy": result["entropy"].tolist(),
    }


def _mfdfa_payload(
    values: object, limits: dict[str, object], profile: str
) -> dict[str, object]:
    result = compute_mfdfa_features(
        values.T,
        scales=(8, 16),
        profile=profile,
        batch_size=int(limits["batch_size"]),
        max_vram_gb=float(limits["max_vram_gb"]),
    )
    return {"hq": result["hq"].tolist(), "scales": list(result["scales"])}


def _signature_payload(
    values: object, limits: dict[str, object], profile: str
) -> dict[str, object]:
    result = compute_signature_features(
        values.reshape(1, values.shape[0], values.shape[1]),
        profile=profile,
        batch_size=int(limits["batch_size"]),
        max_vram_gb=float(limits["max_vram_gb"]),
    )
    return {
        "order_one": result["order_one"].tolist(),
        "order_two_shape": list(result["order_two"].shape),
    }


def _graph_payload(
    values: object, limits: dict[str, object], profile: str
) -> dict[str, object]:
    result = compute_graph_features(
        values,
        profile=profile,
        batch_size=int(limits["batch_size"]),
        max_vram_gb=float(limits["max_vram_gb"]),
    )
    return {"edges": result["edges"], "pagerank": result["pagerank"].tolist()}


def _manifest(
    profile: str,
    limits: dict[str, object],
    artifacts: dict[str, str],
    warnings: list[str],
    enable_micro_gpu: bool,
    queue: bool,
) -> dict[str, object]:
    return {
        "profile": profile,
        "tasks": list(LOCAL_SIMPLE_TASKS),
        "limits": limits,
        "artifacts": artifacts,
        "warnings": warnings,
        "enable_micro_gpu": enable_micro_gpu,
        "queue": queue,
        "heavy_tasks_executed": False,
    }


def _sample_values() -> object:
    np = _numpy_module()
    time = np.arange(128, dtype=float)
    columns = [100 + time * 0.1, 80 + time * 0.08, 50 + time * 0.05, 110 - time * 0.02]
    return np.stack(columns, axis=1)


def _shape_payload(panel: dict[str, object]) -> dict[str, object]:
    return {"symbols": list(panel["symbols"]), "shape": list(panel["values"].shape)}


def _task_config(max_vram_gb: float | None) -> dict[str, object]:
    return {"batch_size": 64, "window": 128, "max_vram_gb": max_vram_gb or ""}


def _write_json(output_path: Path, payload: dict[str, object]) -> Path:
    output_path.write_text(json.dumps(_json_ready(payload), indent=2), encoding="utf-8")
    return output_path


def _json_ready(value: object) -> object:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _write_parquet_rows(rows: list[dict[str, object]], output_path: Path) -> bool:
    try:
        import pyarrow
        import pyarrow.parquet
    except ImportError:
        return False
    table = pyarrow.Table.from_pylist(rows)
    pyarrow.parquet.write_table(table, output_path)
    return True


def _validate_local_profile(profile: str) -> None:
    if profile not in ("local_cpu_low", "local_mx350_queue", "local_rtx4060ti"):
        message = f"Invalid local profile {profile!r}; expected local compute profile"
        raise ValueError(message)


def _numpy_module() -> object:
    try:
        import numpy
    except ImportError as error:
        message = "Local simple pipeline requires numpy; expected installed package"
        raise RuntimeError(message) from error
    return numpy
