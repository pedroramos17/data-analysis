"""JSON manifest helpers for portable cloud jobs."""

from datetime import UTC, datetime
from pathlib import Path
import json
from collections.abc import Mapping


def utc_timestamp() -> str:
    """Return a manifest-friendly UTC timestamp.

    Example:
        `timestamp = utc_timestamp()`
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write_manifest(payload: Mapping[str, object], output_path: Path) -> Path:
    """Write a stable JSON manifest payload.

    Example:
        `write_manifest({"ok": True}, Path("manifest.json"))`
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(dict(payload), indent=2, sort_keys=True)
    output_path.write_text(text, encoding="utf-8")
    return output_path


def read_manifest(input_path: Path) -> dict[str, object]:
    """Read a JSON manifest payload.

    Example:
        `payload = read_manifest(Path("job.json"))`
    """
    if not input_path.exists():
        raise RuntimeError(f"Missing manifest {input_path!s}; expected JSON file")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid manifest {input_path!s}; expected JSON object")
    return payload


def result_manifest(
    job_spec: Mapping[str, object],
    status: str,
    return_code: int,
    output_path: Path,
) -> dict[str, object]:
    """Build a result manifest for a completed cloud job command.

    Example:
        `payload = result_manifest(job, "success", 0, Path("result.json"))`
    """
    return {
        "schema_version": "1.0",
        "job_name": str(job_spec.get("job_name", "")),
        "task": str(job_spec.get("task", "")),
        "status": status,
        "return_code": return_code,
        "outputs": dict(_mapping(job_spec.get("outputs", {}))),
        "created_at": utc_timestamp(),
        "result_manifest_path": str(output_path),
    }


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}

