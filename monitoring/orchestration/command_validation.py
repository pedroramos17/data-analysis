"""Validation for dashboard-managed Django management commands."""

import shlex
import sys
from pathlib import Path


DENIED_MANAGEMENT_COMMANDS = {
    "dbshell",
    "flush",
    "makemigrations",
    "migrate",
    "shell",
    "sqlmigrate",
}
SHELL_OPERATOR_TOKENS = ("|", ">", "<", "&&", "||", ";", "`", "$(")


def validate_management_command(command: str) -> list[str]:
    """Return safe subprocess args for a dashboard job command.

    Example:
        `validate_management_command("python manage.py inspect_compute")`
    """
    _reject_shell_operators(command)
    tokens = shlex.split(command)
    if len(tokens) < 2:
        raise ValueError(f"Invalid command {command!r}; expected manage.py command")
    args = _normalize_manage_py_tokens(tokens, command)
    command_name = _management_command_name(args, command)
    _reject_denied_command(command_name, command)
    return args


def _reject_shell_operators(command: str) -> None:
    for token in SHELL_OPERATOR_TOKENS:
        if token in command:
            message = f"Invalid command {command!r}; expected no shell operator {token}"
            raise ValueError(message)


def _normalize_manage_py_tokens(tokens: list[str], command: str) -> list[str]:
    first = Path(tokens[0]).name.lower()
    if first in ("python", "python3"):
        return _python_manage_tokens(tokens, command)
    if first == "manage.py":
        return [sys.executable, *tokens]
    raise ValueError(f"Invalid command {command!r}; expected python manage.py ...")


def _python_manage_tokens(tokens: list[str], command: str) -> list[str]:
    if len(tokens) < 3 or Path(tokens[1]).name != "manage.py":
        raise ValueError(f"Invalid command {command!r}; expected python manage.py ...")
    return [sys.executable, *tokens[1:]]


def _management_command_name(args: list[str], command: str) -> str:
    if len(args) < 3:
        raise ValueError(f"Invalid command {command!r}; expected management subcommand")
    return args[2]


def _reject_denied_command(command_name: str, command: str) -> None:
    if command_name in DENIED_MANAGEMENT_COMMANDS:
        expected = ", ".join(sorted(DENIED_MANAGEMENT_COMMANDS))
        message = f"Invalid command {command!r}; denied management command in {expected}"
        raise ValueError(message)
