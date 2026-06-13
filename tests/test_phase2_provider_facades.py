"""Phase 2 provider facade contract tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.config.settings import QueueSettings, StorageSettings, load_runtime_settings
from src.providers.base import ProviderError
from src.providers.compute.dry_run import DryRunComputeProvider
from src.providers.compute.runpod import RunPodComputeProvider
from src.providers.queue.local import LocalQueueProvider
from src.providers.queue.redis import RedisQueueProvider
from src.providers.registry import build_provider_registry
from src.providers.storage.local import LocalStorageProvider
from src.providers.storage.s3_compatible import S3CompatibleStorageProvider

ROOT = Path(__file__).resolve().parents[1]


class Phase2ProviderFacadeTests(unittest.TestCase):
    """Cloud-facing facades should stay explicit and local-safe by default."""

    def test_stub_compute_uses_generic_dry_run_provider(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(
                env={"COMPUTE_PROVIDER": "stub"},
                base_dir=Path(temp_dir),
            )
            compute = build_provider_registry(settings).get_compute()

        self.assertIsInstance(compute, DryRunComputeProvider)
        submission = compute.submit_job({"name": "train", "payload": {"model": "test"}})

        self.assertEqual(submission.status, "PLANNED")
        self.assertTrue(submission.metadata["dry_run"])
        self.assertFalse(submission.metadata["launches_paid_infrastructure"])
        self.assertEqual(compute.estimate_cost({})["estimated_cost_usd"], 0.0)
        self.assertEqual(compute.terminate_idle()["terminated"], 0)
        self.assertTrue(compute.healthcheck())

    def test_runpod_phase2_methods_are_dry_run_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(
                env={
                    "APP_ENV": "cloud",
                    "DEPLOYMENT_MODE": "cloud_gpu",
                    "RUNPOD_DRY_RUN": "true",
                    "MAX_GPU_HOURLY_COST_USD": "0.75",
                },
                base_dir=Path(temp_dir),
            )
            compute = build_provider_registry(settings).get_compute()

        self.assertIsInstance(compute, RunPodComputeProvider)
        submission = compute.submit_job({"name": "train", "max_runtime_seconds": 1800})

        self.assertEqual(submission.status, "PLANNED")
        self.assertIn("dry-run manifest", " ".join(compute.stream_logs(submission.job_id)))
        self.assertEqual(compute.terminate_idle()["terminated"], 0)
        self.assertEqual(
            compute.estimate_cost({"max_runtime_seconds": 1800})["estimated_cost_usd"],
            0.375,
        )
        self.assertEqual(compute.cancel_job(submission.job_id).status, "CANCELLED")
        self.assertTrue(compute.healthcheck())

    def test_real_runpod_launch_requires_api_key(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(
                env={"COMPUTE_PROVIDER": "runpod", "RUNPOD_DRY_RUN": "false"},
                base_dir=Path(temp_dir),
            )
            compute = build_provider_registry(settings).get_compute()

        with self.assertRaisesRegex(ProviderError, "RUNPOD_API_KEY"):
            compute.submit_job({"name": "train"})

    def test_local_storage_put_file_and_get_file_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "lake"
            source = Path(temp_dir) / "source.txt"
            target = Path(temp_dir) / "downloaded.txt"
            source.write_text("feature-data", encoding="utf-8")
            storage = LocalStorageProvider(root)

            uri = storage.put_file(source, "features/source.txt")
            downloaded = storage.get_file("features/source.txt", target)

            self.assertTrue(uri.startswith("file:"))
            self.assertTrue(storage.exists("features/source.txt"))
            self.assertEqual(downloaded.read_text(encoding="utf-8"), "feature-data")

    def test_s3_provider_reports_missing_configuration_before_boto3(self) -> None:
        provider = S3CompatibleStorageProvider(
            StorageSettings(provider="s3", local_root=ROOT / "data"),
        )

        with self.assertRaisesRegex(ProviderError, "OBJECT_STORAGE_BUCKET"):
            provider.put_bytes("x", b"1")

    def test_local_queue_supports_retry_and_dead_letter(self) -> None:
        queue = LocalQueueProvider()
        first_id = queue.publish("jobs", {"id": 1})

        with self.assertRaisesRegex(RuntimeError, "retry me"):
            queue.consume("jobs", lambda payload: _raise("retry me"))

        self.assertTrue(queue.retry(first_id))
        handled: list[dict[str, object]] = []
        self.assertEqual(queue.consume("jobs", lambda payload: handled.append(dict(payload))), 1)
        self.assertEqual(handled, [{"id": 1}])

        second_id = queue.publish("jobs", {"id": 2})
        with self.assertRaisesRegex(RuntimeError, "dead letter me"):
            queue.consume("jobs", lambda payload: _raise("dead letter me"))

        self.assertTrue(queue.dead_letter(second_id))
        self.assertFalse(queue.retry(second_id))

    def test_memory_rate_limit_blocks_after_configured_window_capacity(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(
                env={"RATE_LIMIT_REQUESTS_PER_MINUTE": "1", "RATE_LIMIT_BURST": "0"},
                base_dir=Path(temp_dir),
            )
            limiter = build_provider_registry(settings).get_rate_limit()

        first = limiter.allow("ingest")
        second = limiter.allow("ingest")

        self.assertTrue(first.allowed)
        self.assertEqual(first.remaining, 0)
        self.assertFalse(second.allowed)
        limiter.reset("ingest")
        self.assertTrue(limiter.allow("ingest").allowed)

    def test_redis_queue_and_rate_limit_require_explicit_urls(self) -> None:
        queue = RedisQueueProvider(QueueSettings(provider="redis"))
        with self.assertRaisesRegex(ProviderError, "REDIS_URL or QUEUE_URL"):
            queue.healthcheck()

        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(
                env={"RATE_LIMIT_PROVIDER": "redis"},
                base_dir=Path(temp_dir),
            )
            limiter = build_provider_registry(settings).get_rate_limit()

        with self.assertRaisesRegex(ProviderError, "RATE_LIMIT_REDIS_URL or REDIS_URL"):
            limiter.healthcheck()

    def test_missing_postgres_and_object_storage_settings_are_clear(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "DATABASE_URL"):
                load_runtime_settings(
                    env={
                        "APP_ENV": "cloud",
                        "DEPLOYMENT_MODE": "cloud_mvp",
                        "STORAGE_PROVIDER": "local",
                    },
                    base_dir=Path(temp_dir),
                )

            with self.assertRaisesRegex(ValueError, "OBJECT_STORAGE_BUCKET"):
                load_runtime_settings(
                    env={
                        "APP_ENV": "cloud",
                        "DEPLOYMENT_MODE": "cloud_mvp",
                        "DB_MODE": "sqlite",
                    },
                    base_dir=Path(temp_dir),
                )

    def test_business_logic_does_not_import_runpod_sdk_directly(self) -> None:
        offenders: list[str] = []
        for path in (ROOT / "src").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "import runpod" in text or "from runpod" in text:
                offenders.append(path.relative_to(ROOT).as_posix())

        self.assertEqual(offenders, [])


def _raise(message: str) -> None:
    raise RuntimeError(message)


if __name__ == "__main__":
    unittest.main()
