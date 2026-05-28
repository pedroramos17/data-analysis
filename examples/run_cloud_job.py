#!/usr/bin/env python
"""Run a portable cloud job spec in the current environment."""

from pathlib import Path
import argparse
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from monitoring.cloud.jobs import validate_budget_guard  # noqa: E402
from monitoring.cloud.manifest import (  # noqa: E402
    read_manifest,
    result_manifest,
    write_manifest,
)
from monitoring.orchestration.command_validation import (  # noqa: E402
    validate_management_command,
)

ALLOWED_EXPERIMENT_SCRIPTS = {
    "experiments/mamba/train_smoke.py",
    "experiments/nrde/train_smoke.py",
    "experiments/glc_gnn/train_smoke.py",
}
CLOUD_RUNNER_SHELL_TOKENS = ("|", ">", "<", "&&", "||", ";", "`", "$(")


def validate_cloud_runner_command(command: str) -> list[str]:
    """Return safe subprocess args for a portable cloud job command.

    Example:
        `validate_cloud_runner_command("python manage.py inspect_compute")`
    """
    _reject_cloud_shell_operators(command)
    tokens = shlex.split(command)
    if len(tokens) < 2:
        raise ValueError(f"Invalid command {command!r}; expected safe python command")
    if _is_manage_py_command(tokens):
        return validate_management_command(command)
    if _is_experiment_command(tokens):
        return [sys.executable, *tokens[1:]]
    expected = "python manage.py ... or python experiments/<name>/train_smoke.py ..."
    raise ValueError(f"Invalid command {command!r}; expected {expected}")


def _reject_cloud_shell_operators(command: str) -> None:
    for token in CLOUD_RUNNER_SHELL_TOKENS:
        if token in command:
            message = f"Invalid command {command!r}; expected no shell operator {token}"
            raise ValueError(message)


def _is_manage_py_command(tokens: list[str]) -> bool:
    return Path(tokens[0]).name.lower() in {"python", "python3"} and (
        len(tokens) >= 3 and Path(tokens[1]).name == "manage.py"
    )


def _is_experiment_command(tokens: list[str]) -> bool:
    if Path(tokens[0]).name.lower() not in {"python", "python3"}:
        return False
    script = Path(tokens[1]).as_posix()
    return script in ALLOWED_EXPERIMENT_SCRIPTS


def main() -> int:
    """Run the cloud job CLI.

    Example:
        `python examples/run_cloud_job.py --job-spec exports/job.json --confirm`
    """
    args = _parse_args()
    job_spec = read_manifest(args.job_spec)
    validate_budget_guard(job_spec)
    _validate_inputs(job_spec)
    if _requires_confirmation(job_spec) and not args.confirm:
        _write_refusal(job_spec, args.result_manifest)
        return 2
    return _execute_or_dry_run(job_spec, args)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-spec", type=Path, required=True)
    parser.add_argument(
        "--result-manifest", type=Path, default=Path("result_manifest.json")
    )
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _validate_inputs(job_spec: dict[str, object]) -> None:
    inputs = job_spec.get("inputs", {})
    if not isinstance(inputs, dict):
        raise ValueError(f"Invalid inputs {inputs!r}; expected JSON object")
    for input_path in _existing_path_values(inputs):
        if not Path(input_path).exists():
            raise RuntimeError(f"Missing input {input_path!r}; expected existing file")


def _existing_path_values(inputs: dict[str, object]) -> tuple[str, ...]:
    paths = []
    for value in inputs.values():
        text = str(value)
        if text.startswith("exports/") or text.endswith((".parquet", ".json", ".npz")):
            paths.append(text)
    return tuple(paths)


def _requires_confirmation(job_spec: dict[str, object]) -> bool:
    budget = job_spec.get("budget", {})
    if not isinstance(budget, dict):
        return True
    return budget.get("require_confirmation") is True


def _write_refusal(job_spec: dict[str, object], output_path: Path) -> None:
    payload = result_manifest(job_spec, "confirmation_required", 2, output_path)
    write_manifest(payload, output_path)


def _execute_or_dry_run(job_spec: dict[str, object], args: argparse.Namespace) -> int:
    command = str(job_spec.get("command", ""))
    if not command:
        raise ValueError(f"Invalid command {command!r}; expected non-empty string")
    if args.dry_run:
        payload = result_manifest(job_spec, "dry_run", 0, args.result_manifest)
        write_manifest(payload, args.result_manifest)
        return 0
    args_list = validate_cloud_runner_command(command)
    completed = subprocess.run(args_list, check=False, cwd=ROOT)
    status = "success" if completed.returncode == 0 else "failed"
    payload = result_manifest(
        job_spec, status, completed.returncode, args.result_manifest
    )
    write_manifest(payload, args.result_manifest)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
