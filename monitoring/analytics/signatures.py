"""Simple batched signature features."""

from monitoring.compute.array_api import as_float_array, free_device_cache


def compute_signature_features(
    values: object,
    backend: str = "auto",
    profile: str = "local_cpu_low",
    batch_size: int = 64,
    precision: str = "float32",
    max_vram_gb: float | None = None,
    partition: str = "",
) -> dict[str, object]:
    """Compute order-1 and order-2 path signature features.

    Example:
        `features = compute_signature_features([[[1, 2], [2, 3]]])`
    """
    paths = _as_batch_time_channel(values, precision)
    increments = paths[:, 1:, :] - paths[:, :-1, :]
    order_one = increments.sum(axis=1)
    order_two = _order_two_interactions(increments)
    if profile == "local_mx350_queue":
        free_device_cache(backend)
    return _payload(
        order_one, order_two, backend, profile, batch_size, max_vram_gb, partition
    )


def _as_batch_time_channel(values: object, precision: str) -> object:
    array = as_float_array(values, precision)
    if array.ndim == 2:
        return array.reshape(1, array.shape[0], array.shape[1])
    if array.ndim == 3:
        return array
    message = (
        f"Invalid signature shape {array.shape!r}; "
        "expected [batch, time, channels]"
    )
    raise ValueError(message)


def _order_two_interactions(increments: object) -> object:
    np = _numpy_module()
    return np.einsum("btc,btd->bcd", increments, increments) / 2.0


def _payload(
    order_one: object,
    order_two: object,
    backend: str,
    profile: str,
    batch_size: int,
    max_vram_gb: float | None,
    partition: str,
) -> dict[str, object]:
    return {
        "order_one": order_one,
        "order_two": order_two,
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
        message = "Signature features require numpy; expected installed package"
        raise RuntimeError(message) from error
    return numpy
