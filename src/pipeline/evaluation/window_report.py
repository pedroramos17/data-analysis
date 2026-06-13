"""JSON and Markdown report writers for Phase 8."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from src.security.secret_redaction import env_secret_values, redact_secrets


def write_window_report(report: Mapping[str, object], output_dir: Path) -> dict[str, str]:
    """Write one window report in JSON and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "window_report.json"
    md_path = output_dir / "window_report.md"
    safe_report = redact_secrets(dict(report), env_secret_values())
    json_path.write_text(json.dumps(safe_report, sort_keys=True, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_markdown_report(safe_report, title=f"Window {report.get('window_id')} Report"), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def write_aggregate_report(report: Mapping[str, object], output_dir: Path) -> dict[str, str]:
    """Write aggregate report in JSON and Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evaluation_report.json"
    md_path = output_dir / "evaluation_report.md"
    safe_report = redact_secrets(dict(report), env_secret_values())
    json_path.write_text(json.dumps(safe_report, sort_keys=True, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_markdown_report(safe_report, title="Evaluation Report"), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _markdown_report(report: Mapping[str, object], title: str) -> str:
    lines = [f"# {title}", ""]
    for key, value in report.items():
        lines.append(f"## {key}")
        if isinstance(value, Mapping):
            lines.extend(_mapping_lines(value))
        elif isinstance(value, list):
            lines.append(f"Items: {len(value)}")
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _mapping_lines(mapping: Mapping[str, object]) -> list[str]:
    lines: list[str] = []
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            lines.append(f"- {key}: {json.dumps(dict(value), sort_keys=True, default=str)}")
        else:
            lines.append(f"- {key}: {value}")
    return lines
