"""Backend names and selected backend value objects."""

from dataclasses import dataclass


KNOWN_BACKENDS = (
    "auto",
    "cpu",
    "cuda",
    "cupy",
    "cloud_manifest",
    "native",
    "gpu",
)


@dataclass(frozen=True, slots=True)
class SelectedBackend:
    """Resolved backend decision for a task and profile.

    Example:
        `SelectedBackend("cpu", "auto", "local_cpu_low", "", True, "fallback")`
    """

    name: str
    requested_backend: str
    profile: str
    device: str
    used_fallback: bool
    reason: str


def normalize_backend_name(backend_name: str) -> str:
    """Normalize a backend alias into a supported backend name.

    Example:
        `normalize_backend_name("gpu")`
    """
    normalized_name = backend_name.strip().lower()
    if normalized_name == "gpu":
        return "cuda"
    if normalized_name not in KNOWN_BACKENDS:
        expected = ", ".join(KNOWN_BACKENDS)
        message = f"Invalid backend {backend_name!r}; expected one of: {expected}"
        raise ValueError(message)
    return normalized_name
