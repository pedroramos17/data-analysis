"""Local filesystem storage provider."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.providers.base import ProviderError


@dataclass(frozen=True, slots=True)
class LocalStorageProvider:
    """Store object bytes under a local root directory.

    Example:
        `LocalStorageProvider(Path("data/lake")).put_bytes("x", b"1")`
    """

    root: Path

    def put_file(self, local_path: str | Path, remote_path: str) -> str:
        """Store a local file under the provider root."""
        return self.put_bytes(remote_path, Path(local_path).read_bytes())

    def get_file(self, remote_path: str, local_path: str | Path) -> Path:
        """Copy a local-provider object to a requested local path."""
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.get_bytes(remote_path))
        return target

    def put_bytes(
        self,
        path: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        """Store bytes and return a `file:` URI."""
        target = self._safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target.resolve().as_uri()

    def get_bytes(self, path: str) -> bytes:
        """Read bytes from a local object path."""
        return self._safe_path(path).read_bytes()

    def exists(self, path: str) -> bool:
        """Return whether a local object path exists."""
        return self._safe_path(path).exists()

    def list(self, prefix: str) -> list[str]:
        """Return local object paths below a prefix."""
        root = self._safe_path(prefix)
        if root.is_file():
            return [_relative_object_path(self.root, root)]
        if not root.exists():
            return []
        return sorted(
            _relative_object_path(self.root, path)
            for path in root.rglob("*")
            if path.is_file()
        )

    def delete(self, path: str) -> None:
        """Delete a local object path if it exists."""
        target = self._safe_path(path)
        if target.exists():
            target.unlink()

    def presign_read(self, path: str, expires_seconds: int) -> str:
        """Return a local `file:` URI for read access."""
        return self._safe_path(path).resolve().as_uri()

    def _safe_path(self, path: str) -> Path:
        normalized = _normalized_object_path(path)
        target = (self.root / normalized).resolve()
        root = self.root.resolve()
        if target == root or root in target.parents:
            return target
        raise ProviderError(f"Invalid storage path {path!r}; expected relative path")


def _normalized_object_path(path: str) -> str:
    value = path.strip().replace("\\", "/").strip("/")
    if not value:
        return "."
    if value and ".." not in Path(value).parts:
        return value
    raise ProviderError(f"Invalid storage path {path!r}; expected relative path")


def _relative_object_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
