"""Optional native kernel build helpers."""

import shutil
import subprocess
import warnings
from pathlib import Path


def find_c_compiler() -> str:
    """Return the first available C compiler path.

    Example:
        `compiler_path = find_c_compiler()`
    """
    for compiler_name in ("cc", "gcc", "clang", "cl"):
        compiler_path = shutil.which(compiler_name)
        if compiler_path:
            return compiler_path
    return ""


def build_optional_kernels(source_path: Path, output_path: Path) -> bool:
    """Compile optional kernels only when a compiler is available.

    Example:
        `build_optional_kernels(Path("kernel.c"), Path("kernel.so"))`
    """
    compiler_path = find_c_compiler()
    if not compiler_path:
        warnings.warn("Native build skipped; expected C compiler on PATH", stacklevel=2)
        return False
    if not source_path.exists():
        _warn_missing_source(source_path)
        return False
    return _compile_shared_library(compiler_path, source_path, output_path)


def _compile_shared_library(
    compiler_path: str, source_path: Path, output_path: Path
) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        compiler_path,
        "-shared",
        "-O2",
        "-fPIC",
        str(source_path),
        "-o",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        warnings.warn(f"Native build failed for {source_path!s}: {error}", stacklevel=2)
        return False
    return True


def _warn_missing_source(source_path: Path) -> None:
    warnings.warn(
        f"Native build skipped for source {source_path!s}; expected existing C file",
        stacklevel=2,
    )
