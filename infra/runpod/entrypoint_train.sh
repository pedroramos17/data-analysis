#!/usr/bin/env sh
set -eu

LOG_DIR="${RUNPOD_LOG_DIR:-/workspace/logs}"
ARTIFACT_DIR="${RUNPOD_ARTIFACT_DIR:-/workspace/artifacts}"
mkdir -p "$LOG_DIR" "$ARTIFACT_DIR"
LOG_FILE="${RUNPOD_LOG_FILE:-$LOG_DIR/train.log}"

redact() {
  sed -E 's/(api[_-]?key|token|secret|password|credential)([=: ][^ ]+)/\1=[REDACTED]/Ig'
}

require_env() {
  name="$1"
  eval "value=\${$name:-}"
  if [ -z "$value" ]; then
    printf '%s\n' "missing required environment variable: $name" | redact >&2
    exit 2
  fi
}

config_value() {
  key="$1"
  python3 - "$CONFIG_PATH" "$key" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
try:
    import yaml
except Exception:
    yaml = None

if not path.exists():
    raise SystemExit(0)
if yaml is not None:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
else:
    data = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if ":" not in raw or raw.lstrip().startswith("#") or raw.startswith(" "):
            continue
        name, value = raw.split(":", 1)
        data[name.strip()] = value.strip().strip('"').strip("'")
value = data.get(key, "") if isinstance(data, dict) else ""
print(value if value is not None else "")
PY
}

validate_config() {
  if [ ! -f "$CONFIG_PATH" ]; then
    printf '%s\n' "training config not found: $CONFIG_PATH" | redact >&2
    exit 2
  fi
  case "$CONFIG_PATH" in
    *.yaml|*.yml|*.json) ;;
    *) printf '%s\n' "training config must be .yaml, .yml, or .json: $CONFIG_PATH" | redact >&2; exit 2 ;;
  esac
  python3 -m src.cli cost estimate --config "$CONFIG_PATH" >/tmp/runpod_cost_validation.json
}

validate_command() {
  python3 - "$COMMAND" <<'PY'
import sys

from src.security.validation import validate_cli_command

try:
    validate_cli_command(sys.argv[1])
except ValueError as exc:
    print(f"invalid training command: {exc}", file=sys.stderr)
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

upload_one() {
  source_path="$1"
  target_uri="$2"
  label="$3"
  if [ -z "$target_uri" ] || [ ! -e "$source_path" ]; then
    return 0
  fi
  python3 - "$source_path" "$target_uri" "$label" <<'PY'
from pathlib import Path
from urllib.parse import urlparse
import os
import shutil
import sys

source = Path(sys.argv[1])
target = sys.argv[2]
label = sys.argv[3]
parsed = urlparse(target)

def copy_tree(dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(source, dst)

if parsed.scheme in ("", "file"):
    copy_tree(Path(parsed.path if parsed.scheme else target))
    print(f"uploaded {label} to {target}")
    raise SystemExit(0)

if parsed.scheme == "s3":
    try:
        import boto3
    except Exception as exc:
        print(f"skipping {label} upload; boto3 unavailable: {exc}")
        raise SystemExit(0)
    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT_URL") or None,
        region_name=os.getenv("OBJECT_STORAGE_REGION") or None,
    )
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")
    files = [source] if source.is_file() else [p for p in source.rglob("*") if p.is_file()]
    for file_path in files:
        suffix = file_path.name if source.is_file() else file_path.relative_to(source).as_posix()
        key = f"{prefix.rstrip('/')}/{suffix}" if prefix else suffix
        client.upload_file(str(file_path), bucket, key)
    print(f"uploaded {label} to {target}")
    raise SystemExit(0)

print(f"skipping {label} upload; unsupported URI scheme: {parsed.scheme}")
PY
}

cleanup() {
  status=$?
  set +e
  logs_uri="${RUNPOD_LOGS_URI:-$(config_value logs_uri)}"
  artifacts_uri="${RUNPOD_ARTIFACTS_URI:-$(config_value output_uri)}"
  metrics_uri="${RUNPOD_METRICS_URI:-$(config_value metrics_uri)}"
  upload_one "$LOG_FILE" "$logs_uri" logs 2>&1 | redact || true
  upload_one "$ARTIFACT_DIR" "$artifacts_uri" artifacts 2>&1 | redact || true
  upload_one /tmp/runpod_cost_validation.json "$metrics_uri" metrics 2>&1 | redact || true
  printf '%s\n' "RunPod training entrypoint exiting with status ${status}" | redact
  exit "$status"
}

term_handler() {
  printf '%s\n' "received termination signal; exiting cleanly" | redact >&2
  exit 143
}

trap cleanup EXIT
trap term_handler INT TERM

CONFIG_PATH="${TRAIN_CONFIG_PATH:-configs/train_gpu_runpod.yaml}"
COMMAND="${TRAIN_COMMAND:-python3 -m src.cli train run-windowed --config ${CONFIG_PATH}}"
export RUNPOD_MAX_RUNTIME_SECONDS="${RUNPOD_MAX_RUNTIME_SECONDS:-3600}"
export RUNPOD_IDLE_TIMEOUT_SECONDS="${RUNPOD_IDLE_TIMEOUT_SECONDS:-300}"

validate_config
validate_command

printf '%s\n' "starting RunPod training command: ${COMMAND}" | redact
RAW_LOG="${LOG_FILE}.raw"
set +e
run_command
command_status=$?
set -e
redact <"$RAW_LOG" | tee "$LOG_FILE"
rm -f "$RAW_LOG"
exit "$command_status"
