"""Atomic write helper for local warehouse files."""

from __future__ import annotations

from pathlib import Path


def replace_text(path: str | Path, content: str) -> Path:
    """Write text through a sibling temp file before replacing the target."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(target)
    return target
