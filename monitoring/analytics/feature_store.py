"""Basic local feature store builders."""

from monitoring.compute.array_api import as_float_array, safe_diff


def build_asset_panel(
    values: object,
    symbols: tuple[str, ...] = ("AAPL", "MSFT", "SPY", "TLT"),
) -> dict[str, object]:
    """Build a simple in-memory asset panel from price-like values.

    Example:
        `panel = build_asset_panel([[1, 2], [2, 3]], ("A", "B"))`
    """
    array = as_float_array(values)
    if array.ndim != 2:
        message = f"Invalid values shape {array.shape!r}; expected [time, assets]"
        raise ValueError(message)
    return {"symbols": symbols[: array.shape[1]], "values": array}


def build_feature_store_basic(
    values: object,
    window: int = 8,
    backend: str = "auto",
    profile: str = "local_cpu_low",
    precision: str = "float32",
) -> dict[str, object]:
    """Build returns and rolling stats for a small local feature store.

    Example:
        `features = build_feature_store_basic([[1, 2], [2, 4]])`
    """
    array = as_float_array(values, precision)
    _validate_window(window, array.shape[0])
    returns = safe_diff(array, axis=0) / _safe_previous(array)
    rolling_mean = _rolling_stat(array, window, "mean")
    rolling_std = _rolling_stat(array, window, "std")
    return _feature_payload(returns, rolling_mean, rolling_std, backend, profile)


def _feature_payload(
    returns: object,
    rolling_mean: object,
    rolling_std: object,
    backend: str,
    profile: str,
) -> dict[str, object]:
    return {
        "returns": returns,
        "rolling_mean": rolling_mean,
        "rolling_std": rolling_std,
        "backend": backend,
        "profile": profile,
    }


def _safe_previous(array: object) -> object:
    np = _numpy_module()
    previous = array[:-1]
    return np.where(previous == 0, 1.0, previous)


def _rolling_stat(array: object, window: int, stat_name: str) -> object:
    np = _numpy_module()
    windows = np.lib.stride_tricks.sliding_window_view(array, window, axis=0)
    if stat_name == "mean":
        return np.nanmean(windows, axis=-1)
    return np.nanstd(windows, axis=-1)


def _validate_window(window: int, length: int) -> None:
    if window <= 1 or window > length:
        message = f"Invalid window {window!r}; expected integer in [2, {length}]"
        raise ValueError(message)


def _numpy_module() -> object:
    try:
        import numpy
    except ImportError as error:
        message = "Feature store requires numpy; expected installed package"
        raise RuntimeError(message) from error
    return numpy
