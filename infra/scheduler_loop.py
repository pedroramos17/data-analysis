"""Shell-free scheduler loop for cloud compose deployments."""

from __future__ import annotations

import os
import subprocess
import sys
import time


def main() -> int:
    """Run due-source ingestion periodically until the container stops."""

    interval_seconds = _positive_int_env("SCHEDULER_INTERVAL_SECONDS", 3600)
    while True:
        subprocess.run(
            [
                sys.executable,
                "manage.py",
                "ingest_due_sources",
                "--limit",
                _positive_int_text_env("SCHEDULER_LIMIT", 20),
            ],
            check=False,
            shell=False,
        )
        time.sleep(interval_seconds)


def _positive_int_env(name: str, default: int) -> int:
    value = _positive_int_text_env(name, default)
    return int(value)


def _positive_int_text_env(name: str, default: int) -> str:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return str(default)
    value = int(raw)
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
