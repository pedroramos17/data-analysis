"""Shared command-string helpers for invoking the project CLI."""

from __future__ import annotations

DEFAULT_PYTHON_EXECUTABLE = "python3"
SRC_CLI_MODULE = "src.cli"


def src_cli_command(*args: object) -> str:
    """Return the canonical `python3 -m src.cli ...` command string."""
    parts = (
        DEFAULT_PYTHON_EXECUTABLE,
        "-m",
        SRC_CLI_MODULE,
        *(str(arg) for arg in args),
    )
    return " ".join(part for part in parts if part)
