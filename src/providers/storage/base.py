"""Storage provider interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StorageProvider(Protocol):
    """Byte-oriented object storage boundary.

    Example:
        `storage.put_bytes("x.txt", b"x")`
    """

    def put_file(self, local_path: str | Path, remote_path: str) -> str:
        """Store a local file and return a provider-neutral URI."""

    def get_file(self, remote_path: str, local_path: str | Path) -> Path:
        """Download a provider path to a local path."""

    def put_bytes(
        self,
        path: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        """Store bytes and return a provider-neutral URI."""

    def get_bytes(self, path: str) -> bytes:
        """Read bytes from the provider path."""

    def exists(self, path: str) -> bool:
        """Return whether a provider path exists."""

    def list(self, prefix: str) -> list[str]:
        """Return paths below a prefix."""

    def delete(self, path: str) -> None:
        """Delete a provider path if it exists."""

    def presign_read(self, path: str, expires_seconds: int) -> str:
        """Return a temporary or local read URI."""
