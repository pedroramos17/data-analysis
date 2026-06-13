"""Input validation for configs, paths, storage keys, and RunPod payloads."""

from __future__ import annotations

import tempfile
import shlex
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

from src.config.settings import RuntimeSettings

CONFIG_SUFFIXES = {".json", ".yaml", ".yml"}
SHELL_COMMAND_KEYS = {"command", "shell_command", "docker_args", "entrypoint"}
STORAGE_URI_KEYS = {"dataset_uri", "output_uri", "logs_uri", "metrics_uri", "artifact_uri"}
PATH_KEYS = {"path", "config_path", "dataset_path", "output_path", "train_path", "validation_path"}
SAFE_CLI_COMMAND_PREFIX = ("python3", "-m", "src.cli")
SHELL_CONTROL_TOKENS = ("\n", "\r", ";", "&&", "||", "|", "`", "$(", ">", "<")


def validate_config_file_path(path: str | Path, allowed_roots: tuple[str, ...] = ("configs",)) -> Path:
    """Validate a CLI config path and return its resolved path."""
    candidate = Path(path)
    if _has_traversal(candidate):
        raise ValueError(f"Invalid config path {path!r}; path traversal is not allowed")
    if candidate.suffix.lower() not in CONFIG_SUFFIXES:
        raise ValueError(f"Invalid config path {path!r}; expected .json, .yaml, or .yml")
    resolved = candidate.resolve()
    if _is_under(resolved, Path(tempfile.gettempdir()).resolve()):
        return resolved
    for root in allowed_roots:
        root_path = Path(root)
        allowed_root = root_path.resolve() if root_path.is_absolute() else (Path.cwd() / root_path).resolve()
        if _is_under(resolved, allowed_root):
            return resolved
    raise ValueError(f"Invalid config path {path!r}; outside allowed config roots")


def validate_uploaded_config(config: Mapping[str, object], settings: RuntimeSettings) -> dict[str, object]:
    """Validate API-uploaded config payloads before execution."""
    payload = dict(config)
    _validate_mapping(payload, settings, path=())
    return payload


def validate_storage_key(path: str, allowed_prefixes: tuple[str, ...]) -> str:
    """Validate a storage object key or URI against traversal and prefix rules."""
    key = _object_key(path)
    if _has_traversal(Path(key)) or Path(key).is_absolute():
        raise ValueError(f"Invalid storage path {path!r}; path traversal is not allowed")
    normalized_key = key.strip().replace("\\", "/").strip("/")
    prefixes = tuple(_normalize_prefix(prefix) for prefix in allowed_prefixes if prefix)
    if prefixes and not any(normalized_key == prefix.rstrip("/") or normalized_key.startswith(prefix) for prefix in prefixes):
        raise ValueError(f"Invalid storage path {path!r}; prefix is not allowed")
    return normalized_key


def validate_cli_command(command: str, *, allow_shell_commands: bool = False) -> str:
    """Validate a configurable command before it reaches shell-capable runtimes."""
    if allow_shell_commands:
        return command
    if any(token in command for token in SHELL_CONTROL_TOKENS):
        raise ValueError("arbitrary shell commands are disabled")
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise ValueError("invalid command syntax") from exc
    if tuple(parts[: len(SAFE_CLI_COMMAND_PREFIX)]) != SAFE_CLI_COMMAND_PREFIX:
        raise ValueError(
            "arbitrary shell commands are disabled; only python3 -m src.cli commands are allowed"
        )
    return command


def _validate_mapping(payload: Mapping[str, object], settings: RuntimeSettings, *, path: tuple[str, ...]) -> None:
    for raw_key, value in payload.items():
        key = str(raw_key)
        normalized = key.lower()
        current_path = (*path, key)
        if isinstance(value, Mapping):
            _validate_mapping(value, settings, path=current_path)
            continue
        if isinstance(value, list | tuple):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    _validate_mapping(item, settings, path=(*current_path, str(index)))
                elif isinstance(item, str):
                    _validate_scalar(normalized, item, settings, current_path)
            continue
        if isinstance(value, str):
            _validate_scalar(normalized, value, settings, current_path)


def _validate_scalar(key: str, value: str, settings: RuntimeSettings, path: tuple[str, ...]) -> None:
    if key in SHELL_COMMAND_KEYS and value:
        try:
            validate_cli_command(value, allow_shell_commands=settings.security.allow_shell_commands)
        except ValueError as exc:
            raise ValueError(f"Invalid config {'.'.join(path)}; {exc}") from exc
    if key in {"image", "runpod_image"} and value and value not in settings.runpod.allowed_images:
        raise ValueError(f"Invalid config {'.'.join(path)}; RunPod image is not allowed")
    if key in STORAGE_URI_KEYS and value:
        validate_storage_key(value, settings.security.allowed_storage_prefixes)
    if key in PATH_KEYS or key.endswith("_path"):
        candidate = Path(value)
        if _has_traversal(candidate) or candidate.is_absolute():
            raise ValueError(f"Invalid config {'.'.join(path)}; path traversal is not allowed")


def _object_key(path_or_uri: str) -> str:
    parsed = urlparse(path_or_uri)
    if parsed.scheme and parsed.netloc:
        return parsed.path.lstrip("/")
    return path_or_uri


def _normalize_prefix(prefix: str) -> str:
    value = prefix.strip().replace("\\", "/").strip("/")
    if not value:
        return ""
    return value + "/"


def _has_traversal(path: Path) -> bool:
    return ".." in path.parts


def _is_under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents
