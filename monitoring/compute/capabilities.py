"""Local capability detection with optional dependency imports."""

import os
import platform
import shutil
import sys
from dataclasses import dataclass
from importlib import metadata, util


@dataclass(frozen=True, slots=True)
class ComputeCapabilities:
    """Detected local compute and optional package capabilities.

    Example:
        `capabilities = detect_compute_capabilities()`
    """

    python_version: str
    os_name: str
    cpu_count: int
    ram_gb: float | None
    pyarrow_available: bool
    pyarrow_version: str
    numpy_available: bool
    numpy_version: str
    torch_available: bool
    torch_version: str
    cuda_available: bool
    cuda_device_name: str
    total_vram_gb: float | None
    cupy_available: bool
    cupy_version: str
    numba_available: bool
    numba_version: str
    c_compiler_available: bool
    c_compiler_path: str


def detect_compute_capabilities() -> ComputeCapabilities:
    """Detect local CPU, memory, GPU, and optional numeric packages.

    Example:
        `detect_compute_capabilities().cuda_available`
    """
    torch_info = _detect_torch_info()
    cupy_info = _detect_cupy_info(torch_info.total_vram_gb)
    compiler_path = _find_c_compiler_path()
    return ComputeCapabilities(
        python_version=_python_version(),
        os_name=platform.platform(),
        cpu_count=os.cpu_count() or 1,
        ram_gb=_detect_ram_gb(),
        pyarrow_available=_module_available("pyarrow"),
        pyarrow_version=_package_version("pyarrow"),
        numpy_available=_module_available("numpy"),
        numpy_version=_package_version("numpy"),
        torch_available=torch_info.available,
        torch_version=torch_info.version,
        cuda_available=torch_info.cuda_available or cupy_info.cuda_available,
        cuda_device_name=torch_info.cuda_device_name or cupy_info.cuda_device_name,
        total_vram_gb=torch_info.total_vram_gb or cupy_info.total_vram_gb,
        cupy_available=cupy_info.available,
        cupy_version=cupy_info.version,
        numba_available=_module_available("numba"),
        numba_version=_package_version("numba"),
        c_compiler_available=bool(compiler_path),
        c_compiler_path=compiler_path,
    )


@dataclass(frozen=True, slots=True)
class _GpuPackageInfo:
    available: bool
    version: str
    cuda_available: bool
    cuda_device_name: str
    total_vram_gb: float | None


def _detect_torch_info() -> _GpuPackageInfo:
    if not _module_available("torch"):
        return _empty_gpu_package_info()
    try:
        import torch
    except Exception:
        return _empty_gpu_package_info()
    cuda_available = bool(torch.cuda.is_available())
    device_name = _torch_device_name(torch, cuda_available)
    total_vram_gb = _torch_total_vram_gb(torch, cuda_available)
    return _GpuPackageInfo(
        True, _package_version("torch"), cuda_available, device_name, total_vram_gb
    )


def _detect_cupy_info(existing_vram_gb: float | None) -> _GpuPackageInfo:
    if not _module_available("cupy"):
        return _empty_gpu_package_info()
    try:
        import cupy
    except Exception:
        return _empty_gpu_package_info()
    device_name = _cupy_device_name(cupy)
    total_vram_gb = existing_vram_gb or _cupy_total_vram_gb(cupy)
    cuda_available = bool(device_name or total_vram_gb)
    return _GpuPackageInfo(
        True, _package_version("cupy"), cuda_available, device_name, total_vram_gb
    )


def _empty_gpu_package_info() -> _GpuPackageInfo:
    return _GpuPackageInfo(False, "", False, "", None)


def _torch_device_name(torch_module: object, cuda_available: bool) -> str:
    if not cuda_available:
        return ""
    try:
        return str(torch_module.cuda.get_device_name(0))
    except Exception:
        return ""


def _torch_total_vram_gb(torch_module: object, cuda_available: bool) -> float | None:
    if not cuda_available:
        return None
    try:
        properties = torch_module.cuda.get_device_properties(0)
        return _bytes_to_gb(float(properties.total_memory))
    except Exception:
        return None


def _cupy_device_name(cupy_module: object) -> str:
    try:
        device = cupy_module.cuda.Device(0)
        attributes = device.attributes
        return str(attributes.get("Name", "")) if isinstance(attributes, dict) else ""
    except Exception:
        return ""


def _cupy_total_vram_gb(cupy_module: object) -> float | None:
    try:
        _free_bytes, total_bytes = cupy_module.cuda.runtime.memGetInfo()
        return _bytes_to_gb(float(total_bytes))
    except Exception:
        return None


def _detect_ram_gb() -> float | None:
    if not hasattr(os, "sysconf"):
        return None
    try:
        pages = float(os.sysconf("SC_PHYS_PAGES"))
        page_size = float(os.sysconf("SC_PAGE_SIZE"))
        return _bytes_to_gb(pages * page_size)
    except (OSError, ValueError, AttributeError):
        return None


def _find_c_compiler_path() -> str:
    for compiler_name in ("cc", "gcc", "clang", "cl"):
        compiler_path = shutil.which(compiler_name)
        if compiler_path:
            return compiler_path
    return ""


def _module_available(module_name: str) -> bool:
    return util.find_spec(module_name) is not None


def _package_version(package_name: str) -> str:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return ""


def _python_version() -> str:
    version = sys.version_info
    return f"{version.major}.{version.minor}.{version.micro}"


def _bytes_to_gb(value: float) -> float:
    return round(value / (1024**3), 2)
