"""Small array API over NumPy with optional Torch, CuPy, and native hooks."""

from dataclasses import dataclass

from monitoring.compute.capabilities import (
    ComputeCapabilities,
    detect_compute_capabilities,
)
from monitoring.compute.profiles import get_compute_profile


@dataclass(frozen=True, slots=True)
class ArrayBackend:
    """Resolved array backend for numeric helpers.

    Example:
        `backend = get_array_backend(profile="local_cpu_low")`
    """

    name: str
    device: str
    profile: str
    notes: tuple[str, ...]


def get_array_backend(
    backend: str = "auto", profile: str = "local_cpu_low"
) -> ArrayBackend:
    """Return a lightweight array backend with CPU fallback.

    Example:
        `get_array_backend("auto", "local_mx350_queue")`
    """
    compute_profile = get_compute_profile(profile)
    capabilities = detect_compute_capabilities()
    if backend.strip().lower() == "auto" and compute_profile.allow_gpu:
        gpu_backend = _gpu_array_backend_or_none(capabilities, profile)
        if gpu_backend is not None:
            return gpu_backend
    backend_name = _normalized_array_backend(
        backend, compute_profile.backend_preference
    )
    if backend_name in ("cuda", "torch", "cupy") and not compute_profile.allow_gpu:
        return _array_backend("numpy", "cpu", profile)
    if _cupy_cuda_available(backend_name, capabilities):
        return _array_backend("cupy", "cuda:0", profile)
    if _torch_cuda_available(backend_name, capabilities):
        return _array_backend("torch", "cuda:0", profile)
    return _array_backend("numpy", "cpu", profile)


def to_numpy(value: object) -> object:
    """Convert an array-like value to a NumPy array.

    Example:
        `array = to_numpy([1, 2, 3])`
    """
    np = _numpy_module()
    if isinstance(value, np.ndarray):
        return value
    if hasattr(value, "detach") and hasattr(value, "cpu"):
        return value.detach().cpu().numpy()
    if hasattr(value, "get"):
        return value.get()
    return np.asarray(value)


def to_device(value: object, backend: str, device: str | None = None) -> object:
    """Move a value to a requested optional backend when available.

    Example:
        `to_device([1, 2, 3], "cpu")`
    """
    backend_name = _normalized_array_backend(backend, "cpu")
    if backend_name == "cupy":
        cupy = _optional_cupy_module()
        return _cupy_array_or_numpy(cupy, value)
    if backend_name in ("cuda", "torch"):
        torch = _optional_torch_module()
        return _torch_tensor_or_numpy(torch, value, device)
    return to_numpy(value)


def as_float_array(value: object, dtype: str = "float32") -> object:
    """Return a NumPy float array with explicit precision.

    Example:
        `as_float_array([1, 2], "float32")`
    """
    _validate_dtype(dtype)
    np = _numpy_module()
    return np.asarray(value, dtype=dtype)


def safe_mean(value: object, axis: int | None = None) -> object:
    """Return a NaN-safe mean.

    Example:
        `safe_mean([1.0, float("nan")])`
    """
    np = _numpy_module()
    return np.nanmean(to_numpy(value), axis=axis)


def safe_std(value: object, axis: int | None = None) -> object:
    """Return a NaN-safe standard deviation.

    Example:
        `safe_std([1.0, float("nan")])`
    """
    np = _numpy_module()
    return np.nanstd(to_numpy(value), axis=axis)


def safe_log(value: object) -> object:
    """Return a finite log by clipping to a positive lower bound.

    Example:
        `safe_log([0.0, 1.0])`
    """
    np = _numpy_module()
    array = np.asarray(to_numpy(value), dtype=float)
    return np.log(np.maximum(array, np.finfo(float).tiny))


def safe_diff(value: object, axis: int = -1) -> object:
    """Return first differences along an axis.

    Example:
        `safe_diff([1, 3, 6])`
    """
    np = _numpy_module()
    return np.diff(to_numpy(value), axis=axis)


def safe_corrcoef(value: object) -> object:
    """Return a finite correlation matrix.

    Example:
        `safe_corrcoef([[1, 2], [2, 3]])`
    """
    np = _numpy_module()
    matrix = np.corrcoef(to_numpy(value), rowvar=False)
    return np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)


def rolling_window_view(value: object, window: int) -> object:
    """Return a rolling window view over the last axis.

    Example:
        `rolling_window_view([1, 2, 3], 2)`
    """
    np = _numpy_module()
    array = np.asarray(to_numpy(value))
    _validate_window(window, array.shape[-1])
    return np.lib.stride_tricks.sliding_window_view(array, window, axis=-1)


def batched_matmul(left: object, right: object) -> object:
    """Return batched matrix multiplication with NumPy fallback.

    Example:
        `batched_matmul([[[1]]], [[[2]]])`
    """
    np = _numpy_module()
    return np.matmul(to_numpy(left), to_numpy(right))


def nan_to_num(value: object) -> object:
    """Replace NaN and infinities with finite values.

    Example:
        `nan_to_num([float("nan")])`
    """
    np = _numpy_module()
    return np.nan_to_num(to_numpy(value), nan=0.0, posinf=0.0, neginf=0.0)


def free_device_cache(backend: str = "auto") -> None:
    """Free optional GPU memory pools when the backend provides them.

    Example:
        `free_device_cache("cuda")`
    """
    if backend.strip().lower() == "auto":
        _free_torch_cache()
        _free_cupy_cache()
        return
    backend_name = _normalized_array_backend(backend, "cpu")
    if backend_name in ("cuda", "torch"):
        _free_torch_cache()
    if backend_name == "cupy":
        _free_cupy_cache()


def _array_backend(name: str, device: str, profile: str) -> ArrayBackend:
    notes = _backend_notes(profile, name)
    return ArrayBackend(name=name, device=device, profile=profile, notes=notes)


def _gpu_array_backend_or_none(
    capabilities: ComputeCapabilities, profile: str
) -> ArrayBackend | None:
    if _torch_cuda_available("cuda", capabilities):
        return _array_backend("torch", "cuda:0", profile)
    if capabilities.cupy_available and capabilities.cuda_available:
        return _array_backend("cupy", "cuda:0", profile)
    return None


def _torch_cuda_available(
    backend_name: str, capabilities: ComputeCapabilities
) -> bool:
    if backend_name not in ("cuda", "torch"):
        return False
    return bool(capabilities.torch_available and capabilities.cuda_available)


def _cupy_cuda_available(
    backend_name: str, capabilities: ComputeCapabilities
) -> bool:
    if backend_name != "cupy":
        return False
    return bool(capabilities.cupy_available and capabilities.cuda_available)


def _backend_notes(profile: str, backend: str) -> tuple[str, ...]:
    if profile == "local_mx350_queue" and backend != "numpy":
        return (
            "MX350 profile: use micro-batches and clear cache after each partition.",
        )
    if profile == "cloud_student" and backend != "numpy":
        return ("Cloud profile: record this device in the job manifest.",)
    return ()


def _normalized_array_backend(backend: str, preferred_backend: str) -> str:
    backend_name = backend.strip().lower()
    if backend_name == "auto":
        return _normalized_array_backend(preferred_backend, "cpu")
    if backend_name in ("cpu", "numpy", "cloud_manifest", "native"):
        return "numpy"
    if backend_name in ("gpu", "cuda", "torch"):
        return "cuda"
    if backend_name == "cupy":
        return "cupy"
    message = (
        f"Invalid array backend {backend!r}; "
        "expected auto, cpu, cuda, cupy, or native"
    )
    raise ValueError(message)


def _torch_tensor_or_numpy(
    torch_module: object | None, value: object, device: str | None
) -> object:
    if torch_module is None:
        return to_numpy(value)
    target_device = device or ("cuda" if torch_module.cuda.is_available() else "cpu")
    return torch_module.as_tensor(value, device=target_device)


def _cupy_array_or_numpy(cupy_module: object | None, value: object) -> object:
    if cupy_module is None:
        return to_numpy(value)
    try:
        return cupy_module.asarray(value)
    except Exception:
        return to_numpy(value)


def _free_torch_cache() -> None:
    torch = _optional_torch_module()
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def _free_cupy_cache() -> None:
    cupy = _optional_cupy_module()
    if cupy is None:
        return
    try:
        cupy.get_default_memory_pool().free_all_blocks()
    except Exception:
        return


def _optional_torch_module() -> object | None:
    try:
        import torch
    except Exception:
        return None
    return torch


def _optional_cupy_module() -> object | None:
    try:
        import cupy
    except Exception:
        return None
    return cupy


def _validate_dtype(dtype: str) -> None:
    if dtype not in ("float16", "float32", "float64"):
        message = f"Invalid dtype {dtype!r}; expected float16, float32, or float64"
        raise ValueError(message)


def _validate_window(window: int, length: int) -> None:
    if window <= 0 or window > length:
        message = f"Invalid window {window!r}; expected integer between 1 and {length}"
        raise ValueError(message)


def _numpy_module() -> object:
    try:
        import numpy
    except ImportError as error:
        message = "NumPy backend unavailable; expected numpy installed"
        raise RuntimeError(message) from error
    return numpy
