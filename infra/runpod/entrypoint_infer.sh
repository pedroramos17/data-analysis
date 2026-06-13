#!/usr/bin/env sh
set -eu

LOG_DIR="${RUNPOD_LOG_DIR:-/workspace/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="${RUNPOD_LOG_FILE:-$LOG_DIR/infer.log}"

redact() {
  sed -E 's/(api[_-]?key|token|secret|password|credential)([=: ][^ ]+)/\1=[REDACTED]/Ig'
}

cleanup() {
  status=$?
  printf '%s\n' "RunPod inference entrypoint exiting with status ${status}" | redact
  exit "$status"
}

term_handler() {
  printf '%s\n' "received termination signal; exiting cleanly" | redact >&2
  exit 143
}

trap cleanup EXIT
trap term_handler INT TERM

CONFIG_PATH="${INFER_CONFIG_PATH:-configs/evaluate.yaml}"
COMMAND="${INFER_COMMAND:-python3 -m src.cli evaluate run --config ${CONFIG_PATH}}"

validate_command() {
  python3 - "$COMMAND" <<'PY'
import sys

from src.security.validation import validate_cli_command

try:
    validate_cli_command(sys.argv[1])
except ValueError as exc:
    print(f"invalid inference command: {exc}", file=sys.stderr)
    raise SystemExit(2)
PY
}

run_command() {
  python3 - "$COMMAND" "$RAW_LOG" <<'PY'
import shlex
import subprocess
import sys

command = sys.argv[1]
log_path = sys.argv[2]
parts = shlex.split(command)
with open(log_path, "wb") as log_file:
    completed = subprocess.run(
        parts,
        check=False,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
raise SystemExit(completed.returncode)
PY
}

if [ ! -f "$CONFIG_PATH" ]; then
  printf '%s\n' "inference config not found: $CONFIG_PATH" | redact >&2
  exit 2
fi
validate_command

printf '%s\n' "starting RunPod inference command: ${COMMAND}" | redact
RAW_LOG="${LOG_FILE}.raw"
set +e
run_command
command_status=$?
set -e
redact <"$RAW_LOG" | tee "$LOG_FILE"
rm -f "$RAW_LOG"
exit "$command_status"
