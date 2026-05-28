"""Small Haar wavelet feature extraction with CPU fallback."""

from monitoring.compute.array_api import as_float_array, free_device_cache


def compute_wavelet_features(
    values: object,
    backend: str = "auto",
    profile: str = "local_cpu_low",
    batch_size: int = 64,
    precision: str = "float32",
    max_vram_gb: float | None = None,
    partition: str = "",
) -> dict[str, object]:
    """Compute simple Haar energy and entropy features.

    Example:
        `features = compute_wavelet_features([[[1, 2, 3, 4]]])`
    """
    array = _as_batch_channel_time(values, precision)
    details = _haar_details(array)
    energies = _detail_energies(details)
    entropy = _scale_entropy(energies)
    if profile == "local_mx350_queue":
        free_device_cache(backend)
    return _feature_payload(
        energies, entropy, backend, profile, batch_size, max_vram_gb, partition
    )


def _as_batch_channel_time(values: object, precision: str) -> object:
    array = as_float_array(values, precision)
    if array.ndim == 1:
        return array.reshape(1, 1, array.shape[0])
    if array.ndim == 2:
        return array.reshape(1, array.shape[1], array.shape[0])
    if array.ndim == 3:
        return array
    message = f"Invalid wavelet shape {array.shape!r}; expected [batch, channels, time]"
    raise ValueError(message)


def _haar_details(array: object) -> tuple[object, ...]:
    current = array
    details = []
    while current.shape[-1] >= 2 and len(details) < 4:
        even = current[..., 0::2]
        odd = current[..., 1::2]
        size = min(even.shape[-1], odd.shape[-1])
        detail = (even[..., :size] - odd[..., :size]) / 2.0
        current = (even[..., :size] + odd[..., :size]) / 2.0
        details.append(detail)
    return tuple(details)


def _detail_energies(details: tuple[object, ...]) -> object:
    np = _numpy_module()
    if not details:
        return np.zeros((1, 1, 1), dtype=float)
    energies = [np.nanmean(detail * detail, axis=-1) for detail in details]
    return np.stack(energies, axis=-1)


def _scale_entropy(energies: object) -> object:
    np = _numpy_module()
    total = np.sum(energies, axis=-1, keepdims=True)
    probabilities = energies / np.where(total == 0, 1.0, total)
    logs = np.log(np.where(probabilities == 0, 1.0, probabilities))
    return -np.sum(probabilities * logs, axis=-1)


def _feature_payload(
    energies: object,
    entropy: object,
    backend: str,
    profile: str,
    batch_size: int,
    max_vram_gb: float | None,
    partition: str,
) -> dict[str, object]:
    return {
        "energy": energies,
        "entropy": entropy,
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
        message = "Wavelet features require numpy; expected installed package"
        raise RuntimeError(message) from error
    return numpy
