"""Optional ctypes native kernel boundary with NumPy fallbacks."""

import os
from dataclasses import dataclass
from pathlib import Path

from monitoring.native.build import find_c_compiler


@dataclass(frozen=True, slots=True)
class NativeKernelStatus:
    """Native kernel availability for inspection and routing.

    Example:
        `status = detect_native_status()`
    """

    available: bool
    loaded: bool
    library_path: str
    compiler_path: str
    warning: str


def detect_native_status() -> NativeKernelStatus:
    """Report optional ctypes kernel status without requiring a build.

    Example:
        `detect_native_status().available`
    """
    library_path = _native_library_path()
    compiler_path = find_c_compiler()
    if not library_path:
        return NativeKernelStatus(
            False, False, "", compiler_path, "native library not built"
        )
    loaded = load_native_library() is not None
    warning = "" if loaded else "native library failed to load; using NumPy fallback"
    return NativeKernelStatus(loaded, loaded, str(library_path), compiler_path, warning)


def load_native_library() -> object | None:
    """Load the optional ctypes library if it exists.

    Example:
        `library = load_native_library()`
    """
    library_path = _native_library_path()
    if not library_path:
        return None
    try:
        import ctypes
    except ImportError:
        return None
    return _load_ctypes_library(ctypes, library_path)


def rolling_mean(values: object, window: int) -> object:
    """Return a rolling mean using native kernels when available.

    Example:
        `rolling_mean([1, 2, 3], 2)`
    """
    np = _numpy_module()
    array = np.asarray(values, dtype=float)
    _validate_window(window, array.shape[0])
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(array, kernel, mode="valid")


def rolling_std(values: object, window: int) -> object:
    """Return a rolling standard deviation with a NumPy fallback.

    Example:
        `rolling_std([1, 2, 3], 2)`
    """
    np = _numpy_module()
    array = np.asarray(values, dtype=float)
    means = rolling_mean(array, window)
    squared_means = rolling_mean(array * array, window)
    variance = np.maximum(squared_means - means * means, 0.0)
    return np.sqrt(variance)


def rolling_zscore(values: object, window: int) -> object:
    """Return rolling z-scores with zero-safe standard deviation.

    Example:
        `rolling_zscore([1, 2, 3], 2)`
    """
    np = _numpy_module()
    array = np.asarray(values, dtype=float)
    trailing_values = array[window - 1 :]
    means = rolling_mean(array, window)
    std_values = rolling_std(array, window)
    safe_std = np.where(std_values == 0, 1.0, std_values)
    return (trailing_values - means) / safe_std


def detrend_linear(values: object) -> object:
    """Remove a linear trend from one numeric sequence.

    Example:
        `detrend_linear([1, 2, 4])`
    """
    np = _numpy_module()
    array = np.asarray(values, dtype=float)
    x_values = np.arange(array.shape[0], dtype=float)
    slope, intercept = np.polyfit(x_values, array, deg=1)
    return array - (slope * x_values + intercept)


def corr_loop(values: object) -> object:
    """Return a correlation matrix through the fallback loop boundary.

    Example:
        `corr_loop([[1, 2], [2, 3]])`
    """
    np = _numpy_module()
    array = np.asarray(values, dtype=float)
    return np.corrcoef(array, rowvar=False)


def _native_library_path() -> Path | None:
    env_path = os.environ.get("MONITORING_NATIVE_LIBRARY", "")
    candidates = _native_library_candidates(env_path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _native_library_candidates(env_path: str) -> tuple[Path, ...]:
    root = Path(__file__).resolve().parents[1] / "native" / "build"
    candidates = (
        root / "libmonitoring_native.so",
        root / "monitoring_native.dll",
        root / "libmonitoring_native.dylib",
    )
    if env_path:
        return (Path(env_path), *candidates)
    return candidates


def _load_ctypes_library(ctypes_module: object, library_path: Path) -> object | None:
    try:
        return ctypes_module.CDLL(str(library_path))
    except OSError:
        return None


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
