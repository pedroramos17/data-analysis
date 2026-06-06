"""RunPod compute provider boundary with secure dry-run defaults."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.cli_commands import src_cli_command
from src.config.settings import RuntimeSettings
from src.providers.base import JobSubmission, ProviderError
from src.security.secret_redaction import redact_secrets, redact_text
from src.security.validation import validate_cli_command

REMOTE_URI_PREFIXES = ("s3://", "r2://", "b2://", "minio://", "gs://")
SENSITIVE_KEY_PARTS = ("api_key", "apikey", "token", "secret", "password", "credential")
SAFE_SECURITY_KEYS = {
    "api_token_logged",
    "redact_secrets",
    "requires_short_lived_storage_credentials",
    "storage_credentials_scope",
}
SENSITIVE_LOG_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|credential)(\s*[=:]\s*)([^\s]+)"
)


@dataclass(slots=True)
class RunPodComputeProvider:
    """Submit RunPod jobs only through explicit budget and security guards.

    Example:
        `RunPodComputeProvider(settings).submit_job({"name": "train"})`
    """

    settings: RuntimeSettings
    _jobs: dict[str, JobSubmission] = field(default_factory=dict)

    def submit_job(self, job_spec: Mapping[str, object]) -> JobSubmission:
        """Create a dry-run manifest or submit a guarded hourly RunPod pod."""
        spec = self._runpod_spec(job_spec)
        dry_run = self._is_dry_run(job_spec)
        cost_estimate = self.estimate_cost(spec)
        self._validate_budget_and_runtime(spec, cost_estimate)
        metadata = self._submission_metadata(spec, cost_estimate, dry_run)
        if dry_run:
            job_id = _runpod_job_id(spec)
            result = JobSubmission(job_id, "PLANNED", metadata)
            self._jobs[job_id] = result
            return result

        self._validate_real_submit(job_spec, spec)
        response = self._deploy_pod(spec)
        job_id = _response_job_id(response) or _runpod_job_id(spec).replace("dryrun", "submit")
        metadata["provider_response"] = _sanitize_for_metadata(response, self._secret_values())
        metadata["provider_job_id"] = job_id
        result = JobSubmission(job_id, "SUBMITTED", metadata)
        self._jobs[job_id] = result
        return result

    def get_status(self, job_id: str) -> JobSubmission:
        """Return known job status, or query RunPod when real mode is active."""
        if job_id in self._jobs:
            return self._jobs[job_id]
        if self.settings.runpod.dry_run or not self.settings.runpod.api_key:
            return JobSubmission(job_id, "UNKNOWN", {})
        response = self._graphql(
            """
            query PodStatus($podId: String!) {
              pod(input: {podId: $podId}) {
                id
                desiredStatus
                lastStatus
                costPerHr
                machineId
              }
            }
            """,
            {"podId": job_id},
        )
        status_payload = _deep_get(response, ("data", "pod")) or {}
        status = str(status_payload.get("lastStatus") or status_payload.get("desiredStatus") or "UNKNOWN")
        return JobSubmission(
            job_id,
            status,
            {"provider": "runpod", "provider_response": _sanitize_for_metadata(status_payload, self._secret_values())},
        )

    def cancel(self, job_id: str) -> JobSubmission:
        """Cancel a planned job or terminate a submitted RunPod pod."""
        if self.settings.runpod.dry_run:
            result = JobSubmission(job_id, "CANCELLED", {"provider": "runpod", "dry_run": True})
            self._jobs[job_id] = result
            return result
        if not self.settings.runpod.api_key:
            raise ProviderError("RUNPOD_API_KEY is required to cancel real RunPod resources")
        response = self._terminate_pod(job_id)
        result = JobSubmission(
            job_id,
            "CANCELLED",
            {"provider": "runpod", "provider_response": _sanitize_for_metadata(response, self._secret_values())},
        )
        self._jobs[job_id] = result
        return result

    def cancel_job(self, job_id: str) -> JobSubmission:
        """Phase 2 alias for `cancel`."""
        return self.cancel(job_id)

    def stream_logs(self, job_id: str) -> list[str]:
        """Return sanitized logs or dry-run planning notes."""
        submission = self.get_status(job_id)
        if submission.status == "UNKNOWN":
            return []
        lines = ["RunPod dry-run manifest only; no pod was launched."] if submission.metadata.get("dry_run") else []
        job_spec = submission.metadata.get("job_spec")
        if isinstance(job_spec, Mapping):
            lines.extend(_extract_log_lines(job_spec))
        return sanitize_runpod_logs(lines, self._secret_values())

    def terminate_idle(self) -> dict[str, object]:
        """Terminate known idle pods or report a dry-run no-op."""
        if self.settings.runpod.dry_run:
            return {"provider": "runpod", "dry_run": True, "terminated": 0}
        if not self.settings.runpod.api_key:
            raise ProviderError("RUNPOD_API_KEY is required to terminate real RunPod resources")

        terminated: list[str] = []
        now = datetime.now(UTC)
        for job_id, submission in list(self._jobs.items()):
            if submission.status not in {"SUBMITTED", "RUNNING"}:
                continue
            heartbeat = str(submission.metadata.get("last_heartbeat_at") or submission.metadata.get("submitted_at") or "")
            if not _is_idle(now, heartbeat, self.settings.runpod.idle_timeout_seconds):
                continue
            self._terminate_pod(job_id)
            terminated.append(job_id)
            self._jobs[job_id] = JobSubmission(job_id, "CANCELLED", {**submission.metadata, "terminated_reason": "idle_timeout"})
        return {"provider": "runpod", "dry_run": False, "terminated": len(terminated), "job_ids": terminated}

    def estimate_cost(self, job_spec: Mapping[str, object]) -> dict[str, object]:
        """Estimate upper-bound RunPod cost without paid infrastructure."""
        runtime_seconds = max(_float_setting(job_spec.get("max_runtime_seconds"), self.settings.runpod.max_runtime_seconds), 0.0)
        runtime_hours = runtime_seconds / 3600.0
        hourly_cost = _float_setting(
            job_spec.get("hourly_cost_usd"),
            min(self.settings.runpod.max_hourly_cost_usd, self.settings.cost.max_gpu_hourly_cost_usd),
        )
        return {
            "provider": "runpod",
            "estimated_runtime_seconds": int(runtime_seconds),
            "estimated_hourly_cost_usd": round(hourly_cost, 4),
            "estimated_cost_usd": round(runtime_hours * hourly_cost, 4),
            "currency": "USD",
            "dry_run": self.settings.runpod.dry_run,
        }

    def healthcheck(self) -> bool:
        """Dry-run is healthy without credentials; real mode needs an API key."""
        return bool(self.settings.runpod.dry_run or self.settings.runpod.api_key)

    def _runpod_spec(self, job_spec: Mapping[str, object]) -> dict[str, object]:
        payload = _json_safe(dict(job_spec.get("payload", {})))
        command = job_spec.get("command") or payload.get("command") or src_cli_command("--help")
        max_runtime_seconds = _int_setting(
            job_spec.get("max_runtime_seconds") or payload.get("max_runtime_seconds"),
            self.settings.runpod.max_runtime_seconds,
        )
        idle_timeout_seconds = _int_setting(
            job_spec.get("idle_timeout_seconds") or payload.get("idle_timeout_seconds"),
            self.settings.runpod.idle_timeout_seconds,
        )
        image = str(job_spec.get("image") or payload.get("image") or self.settings.runpod.image)
        dataset_uri = str(payload.get("dataset_uri") or job_spec.get("dataset_uri") or "")
        output_uri = str(payload.get("output_uri") or job_spec.get("output_uri") or payload.get("artifact_uri") or "")
        logs_uri = str(payload.get("logs_uri") or job_spec.get("logs_uri") or _child_uri(output_uri, "logs"))
        metrics_uri = str(payload.get("metrics_uri") or job_spec.get("metrics_uri") or _child_uri(output_uri, "metrics"))
        hourly_cost = _float_setting(job_spec.get("hourly_cost_usd") or payload.get("hourly_cost_usd"), self.settings.runpod.max_hourly_cost_usd)
        return {
            "schema_version": "1.0",
            "provider": "runpod",
            "name": str(job_spec.get("name", "gpu-job")),
            "task": str(job_spec.get("task", payload.get("task", "training"))),
            "command": str(command),
            "image": image,
            "gpu_type": str(job_spec.get("gpu_type") or payload.get("gpu_type") or self.settings.runpod.gpu_type),
            "min_gpu_memory_gb": _int_setting(
                job_spec.get("min_gpu_memory_gb") or payload.get("min_gpu_memory_gb"),
                self.settings.runpod.min_gpu_memory_gb,
            ),
            "container_disk_gb": self.settings.runpod.container_disk_gb,
            "volume_gb": self.settings.runpod.volume_gb,
            "max_runtime_seconds": max_runtime_seconds,
            "idle_timeout_seconds": idle_timeout_seconds,
            "terminate_on_completion": self.settings.runpod.terminate_on_completion,
            "hourly_cost_usd": hourly_cost,
            "dataset_size_gb": _float_setting(
                job_spec.get("dataset_size_gb") or payload.get("dataset_size_gb"),
                0.0,
            ),
            "model_device": str(job_spec.get("model_device") or payload.get("device") or self.settings.pipeline.model_device),
            "cost_mode": self.settings.pipeline.cost_mode,
            "budget": {
                "max_job_cost_usd": self.settings.cost.max_job_cost_usd,
                "max_gpu_hourly_cost_usd": self.settings.cost.max_gpu_hourly_cost_usd,
                "runpod_max_hourly_cost_usd": self.settings.runpod.max_hourly_cost_usd,
                "require_budget_approval": self.settings.cost.require_budget_approval,
            },
            "runpod": {
                "template_id": self.settings.runpod.template_id,
                "endpoint_id": self.settings.runpod.endpoint_id,
                "network_volume_id": self.settings.runpod.network_volume_id,
                "enable_spot": self.settings.runpod.enable_spot,
            },
            "artifacts": {
                "dataset_uri": dataset_uri,
                "output_uri": output_uri,
                "logs_uri": logs_uri,
                "metrics_uri": metrics_uri,
                "storage_credentials_scope": "read_dataset_write_artifacts",
                "requires_short_lived_storage_credentials": True,
            },
            "autoscaling": {
                "enabled": self.settings.autoscaling.enabled,
                "max_concurrent_gpu_jobs": self.settings.autoscaling.max_concurrent_gpu_jobs,
                "scale_to_zero": self.settings.autoscaling.scale_to_zero,
                "idle_timeout_seconds": self.settings.autoscaling.idle_timeout_seconds,
            },
            "security": {
                "allow_shell_commands": self.settings.security.allow_shell_commands,
                "redact_secrets": self.settings.security.redact_secrets,
                "terminate_remote_on_timeout": self.settings.security.terminate_remote_on_timeout,
                "public_jupyter_enabled": bool(job_spec.get("public_jupyter_enabled", False)),
                "ssh_enabled": bool(job_spec.get("ssh_enabled", False)),
                "api_token_logged": False,
            },
            "payload": payload,
            "launches_paid_infrastructure": False,
        }

    def _is_dry_run(self, job_spec: Mapping[str, object]) -> bool:
        return self.settings.runpod.dry_run or _bool_setting(job_spec.get("dry_run"), False)

    def _submission_metadata(
        self,
        spec: Mapping[str, object],
        cost_estimate: Mapping[str, object],
        dry_run: bool,
    ) -> dict[str, object]:
        safe_spec = _sanitize_for_metadata(spec, self._secret_values())
        safe_spec["launches_paid_infrastructure"] = not dry_run
        return {
            "provider": "runpod",
            "dry_run": dry_run,
            "job_spec": safe_spec,
            "cost_estimate": dict(cost_estimate),
            "submitted_at": datetime.now(UTC).isoformat(),
            "launches_paid_infrastructure": not dry_run,
        }

    def _validate_budget_and_runtime(
        self,
        spec: Mapping[str, object],
        cost_estimate: Mapping[str, object],
    ) -> None:
        max_runtime_seconds = _int_setting(spec.get("max_runtime_seconds"), 0)
        max_allowed_seconds = self.settings.runpod.max_job_minutes * 60
        if max_runtime_seconds <= 0:
            raise ProviderError("RunPod jobs require max_runtime_seconds > 0")
        if max_runtime_seconds > max_allowed_seconds:
            raise ProviderError("RunPod job exceeds RUNPOD_MAX_JOB_MINUTES")
        idle_timeout_seconds = _int_setting(spec.get("idle_timeout_seconds"), 0)
        if idle_timeout_seconds <= 0:
            raise ProviderError("RunPod jobs require RUNPOD_IDLE_TIMEOUT_SECONDS > 0")
        if idle_timeout_seconds > max_runtime_seconds:
            raise ProviderError("RunPod idle timeout cannot exceed max_runtime_seconds")
        if not self.settings.security.terminate_remote_on_timeout:
            raise ProviderError("RunPod jobs require terminate_remote_on_timeout=true")
        image = str(spec.get("image") or "")
        if image not in self.settings.runpod.allowed_images:
            raise ProviderError("RunPod image is not in RUNPOD_ALLOWED_IMAGES")
        if _float_setting(spec.get("hourly_cost_usd"), 0.0) > self.settings.runpod.max_hourly_cost_usd:
            raise ProviderError("RunPod hourly cost exceeds RUNPOD_MAX_HOURLY_COST")
        if _float_setting(cost_estimate.get("estimated_cost_usd"), 0.0) > self.settings.cost.max_job_cost_usd:
            raise ProviderError("RunPod estimated job cost exceeds CLOUD_MAX_JOB_COST_USD")
        if _float_setting(spec.get("dataset_size_gb"), 0.0) > self.settings.runpod.max_dataset_size_gb:
            raise ProviderError("RunPod dataset size exceeds RUNPOD_MAX_DATASET_SIZE_GB")
        try:
            validate_cli_command(
                str(spec.get("command") or ""),
                allow_shell_commands=self.settings.security.allow_shell_commands,
            )
        except ValueError as exc:
            raise ProviderError(f"Invalid RunPod command; {exc}") from exc
        security = spec.get("security") if isinstance(spec.get("security"), Mapping) else {}
        if security.get("public_jupyter_enabled") and not self.settings.runpod.enable_public_jupyter:
            raise ProviderError("RunPod public Jupyter is disabled by default")
        if security.get("ssh_enabled") and not self.settings.runpod.enable_ssh:
            raise ProviderError("RunPod SSH is disabled by default")

    def _validate_real_submit(self, job_spec: Mapping[str, object], spec: Mapping[str, object]) -> None:
        payload = job_spec.get("payload") if isinstance(job_spec.get("payload"), Mapping) else {}
        if not self.settings.runpod.api_key:
            raise ProviderError(
                "RUNPOD_API_KEY is required for real RunPod launches; use "
                "RUNPOD_DRY_RUN=true for manifest-only planning"
            )
        confirm_cost = _bool_setting(job_spec.get("confirm_cost") or payload.get("confirm_cost"), False)
        if not confirm_cost:
            raise ProviderError("Real RunPod submit requires --confirm-cost")
        if self.settings.security.require_signed_job_manifest and not job_spec.get("manifest_signature"):
            raise ProviderError("RunPod submit requires a signed job manifest")
        artifacts = spec.get("artifacts") if isinstance(spec.get("artifacts"), Mapping) else {}
        required_remote = {
            "dataset_uri": artifacts.get("dataset_uri"),
            "output_uri": artifacts.get("output_uri"),
            "logs_uri": artifacts.get("logs_uri"),
            "metrics_uri": artifacts.get("metrics_uri"),
        }
        for name, value in required_remote.items():
            if not _is_remote_uri(str(value or "")):
                raise ProviderError(f"Real RunPod submit requires object storage {name}")

    def _deploy_pod(self, spec: Mapping[str, object]) -> dict[str, object]:
        input_payload: dict[str, object] = {
            "name": str(spec.get("name")),
            "imageName": str(spec.get("image")),
            "gpuTypeId": str(spec.get("gpu_type")),
            "gpuCount": 1,
            "containerDiskInGb": int(spec.get("container_disk_gb") or 40),
            "volumeInGb": int(spec.get("volume_gb") or 0),
            "dockerArgs": str(spec.get("command")),
            "ports": "",
            "env": [
                {"key": "RUNPOD_JOB_SPEC", "value": json.dumps(_sanitize_for_metadata(spec, self._secret_values()), sort_keys=True)},
                {"key": "RUNPOD_MAX_RUNTIME_SECONDS", "value": str(spec.get("max_runtime_seconds"))},
                {"key": "RUNPOD_IDLE_TIMEOUT_SECONDS", "value": str(spec.get("idle_timeout_seconds"))},
            ],
        }
        runpod_cfg = spec.get("runpod") if isinstance(spec.get("runpod"), Mapping) else {}
        if runpod_cfg.get("template_id"):
            input_payload["templateId"] = str(runpod_cfg["template_id"])
        if runpod_cfg.get("network_volume_id"):
            input_payload["networkVolumeId"] = str(runpod_cfg["network_volume_id"])
        if runpod_cfg.get("enable_spot"):
            input_payload["cloudType"] = "SECURE"
            input_payload["startSsh"] = False
            input_payload["supportPublicIp"] = False
            input_payload["dataCenterIds"] = []

        return self._graphql(
            """
            mutation DeployPod($input: PodFindAndDeployOnDemandInput!) {
              podFindAndDeployOnDemand(input: $input) {
                id
                desiredStatus
                lastStatus
                imageName
                machineId
                costPerHr
              }
            }
            """,
            {"input": input_payload},
        )

    def _terminate_pod(self, job_id: str) -> dict[str, object]:
        return self._graphql(
            """
            mutation TerminatePod($podId: String!) {
              podTerminate(input: {podId: $podId}) {
                id
                desiredStatus
                lastStatus
              }
            }
            """,
            {"podId": job_id},
        )

    def _graphql(self, query: str, variables: Mapping[str, object]) -> dict[str, object]:
        payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        request = Request(
            self.settings.runpod.endpoint_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.settings.runpod.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:  # nosec: endpoint is user-configured RunPod API
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise ProviderError(_sanitize_text(f"RunPod API error: {detail}", self._secret_values())) from exc
        except URLError as exc:
            raise ProviderError(_sanitize_text(f"RunPod API unavailable: {exc}", self._secret_values())) from exc
        parsed = json.loads(body or "{}")
        if parsed.get("errors"):
            raise ProviderError(_sanitize_text(f"RunPod API error: {parsed['errors']}", self._secret_values()))
        return parsed

    def _secret_values(self) -> tuple[str, ...]:
        return tuple(value for value in (self.settings.runpod.api_key,) if value)


def sanitize_runpod_logs(lines: Iterable[str], secret_values: Iterable[str] = ()) -> list[str]:
    """Redact API keys and secret-looking assignments from log lines."""
    return [_sanitize_text(str(line), tuple(secret_values)) for line in lines]


def _runpod_job_id(job_spec: Mapping[str, object]) -> str:
    payload = json.dumps(job_spec, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"runpod-dryrun-{digest[:16]}"


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _sanitize_for_metadata(value: object, secret_values: Iterable[str]) -> Any:
    return redact_secrets(value, secret_values)


def _sanitize_text(value: str, secret_values: Iterable[str]) -> str:
    return redact_text(value, secret_values)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in SAFE_SECURITY_KEYS:
        return False
    if normalized in SENSITIVE_KEY_PARTS:
        return True
    return any(normalized.endswith(f"_{part}") for part in SENSITIVE_KEY_PARTS)


def _extract_log_lines(job_spec: Mapping[str, object]) -> list[str]:
    payload = job_spec.get("payload") if isinstance(job_spec.get("payload"), Mapping) else {}
    raw_lines = payload.get("log_lines") or job_spec.get("log_lines") or []
    if isinstance(raw_lines, str):
        return raw_lines.splitlines()
    if isinstance(raw_lines, Iterable):
        return [str(line) for line in raw_lines]
    return []


def _response_job_id(response: Mapping[str, object]) -> str:
    payload = _deep_get(response, ("data", "podFindAndDeployOnDemand"))
    if isinstance(payload, Mapping):
        return str(payload.get("id") or "")
    return ""


def _deep_get(value: Mapping[str, object], keys: tuple[str, ...]) -> object:
    current: object = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _is_idle(now: datetime, timestamp: str, idle_timeout_seconds: int) -> bool:
    if not timestamp:
        return False
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (now - parsed).total_seconds() >= idle_timeout_seconds


def _int_setting(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _float_setting(value: object, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _bool_setting(value: object, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_remote_uri(value: str) -> bool:
    return value.startswith(REMOTE_URI_PREFIXES)


def _child_uri(uri: str, child: str) -> str:
    if not uri:
        return ""
    return uri.rstrip("/") + "/" + child
