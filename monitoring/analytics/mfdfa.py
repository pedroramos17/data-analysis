"""Small batched MFDFA implementation for local validation."""

from monitoring.compute.array_api import as_float_array, free_device_cache


def compute_mfdfa_features(
    values: object,
    q_values: tuple[float, ...] = (2.0,),
    scales: tuple[int, ...] = (8, 16, 32),
    backend: str = "auto",
    profile: str = "local_cpu_low",
    batch_size: int = 64,
    precision: str = "float32",
    max_vram_gb: float | None = None,
    partition: str = "",
) -> dict[str, object]:
    """Compute small MFDFA fluctuation and h(q) estimates.

    Example:
        `features = compute_mfdfa_features([[1, 2, 3, 4, 5, 6, 7, 8]])`
    """
    series = _as_batch_time(values, precision)
    profile_values = _cumulative_profile(series)
    fluctuations = _fluctuations(profile_values, scales, q_values)
    hq = _loglog_slopes(fluctuations, scales)
    if profile == "local_mx350_queue":
        free_device_cache(backend)
    return _payload(
        fluctuations, hq, q_values, scales, backend, profile, batch_size,
        max_vram_gb, partition
    )


def _as_batch_time(values: object, precision: str) -> object:
    array = as_float_array(values, precision)
    if array.ndim == 1:
        return array.reshape(1, array.shape[0])
    if array.ndim == 2:
        return array
    raise ValueError(f"Invalid MFDFA shape {array.shape!r}; expected [batch, time]")


def _cumulative_profile(series: object) -> object:
    np = _numpy_module()
    centered = series - np.nanmean(series, axis=1, keepdims=True)
    return np.cumsum(centered, axis=1)


def _fluctuations(
    profile_values: object,
    scales: tuple[int, ...],
    q_values: tuple[float, ...],
) -> object:
    np = _numpy_module()
    rows = [_scale_fluctuations(profile_values, scale, q_values) for scale in scales]
    return np.stack(rows, axis=1)


def _scale_fluctuations(
    profile_values: object, scale: int, q_values: tuple[float, ...]
) -> object:
    np = _numpy_module()
    segments = _segments(profile_values, scale)
    rms = np.stack([_segment_rms(segment) for segment in segments], axis=1)
    return np.stack([_q_fluctuation(rms, q_value) for q_value in q_values], axis=1)


def _segments(profile_values: object, scale: int) -> list[object]:
    if scale <= 1 or scale > profile_values.shape[1]:
        raise ValueError(f"Invalid scale {scale!r}; expected between 2 and time length")
    count = profile_values.shape[1] // scale
    return [
        profile_values[:, index * scale : (index + 1) * scale]
        for index in range(count)
    ]


def _segment_rms(segment: object) -> object:
    np = _numpy_module()
    x_values = np.arange(segment.shape[1], dtype=float)
    fitted = np.stack([_linear_fit(x_values, row) for row in segment], axis=0)
    return np.sqrt(np.nanmean((segment - fitted) ** 2, axis=1))


def _linear_fit(x_values: object, row: object) -> object:
    np = _numpy_module()
    slope, intercept = np.polyfit(x_values, row, deg=1)
    return slope * x_values + intercept


def _q_fluctuation(rms: object, q_value: float) -> object:
    np = _numpy_module()
    safe = np.maximum(rms, np.finfo(float).tiny)
    if q_value == 0:
        return np.exp(0.5 * np.nanmean(np.log(safe * safe), axis=1))
    return np.nanmean(safe**q_value, axis=1) ** (1.0 / q_value)


def _loglog_slopes(fluctuations: object, scales: tuple[int, ...]) -> object:
    np = _numpy_module()
    log_scales = np.log(np.asarray(scales, dtype=float))
    slopes = [
        _batch_slopes(log_scales, fluctuations[:, :, q])
        for q in range(fluctuations.shape[2])
    ]
    return np.stack(slopes, axis=1)


def _batch_slopes(x_values: object, values: object) -> object:
    np = _numpy_module()
    return np.asarray([_row_slope(x_values, row) for row in values])


def _row_slope(x_values: object, row: object) -> float:
    np = _numpy_module()
    return float(np.polyfit(x_values, np.log(np.maximum(row, 1e-12)), 1)[0])


def _payload(
    fluctuations: object,
    hq: object,
    q_values: tuple[float, ...],
    scales: tuple[int, ...],
    backend: str,
    profile: str,
    batch_size: int,
    max_vram_gb: float | None,
    partition: str,
) -> dict[str, object]:
    return {
        "fluctuations": fluctuations,
        "hq": hq,
        "q_values": q_values,
        "scales": scales,
        "backend": backend,
        "profile": profile,
        "batch_size": batch_size,
        "max_vram_gb": max_vram_gb,
        "partition": partition,
    }


def _numpy_module() -> object:
    try:
        import numpy
    except ImportError as error:
        message = "MFDFA requires numpy; expected installed package"
        raise RuntimeError(message) from error
    return numpy
