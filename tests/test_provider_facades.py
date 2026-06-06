"""Dependency-light tests for local provider facades."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.config.settings import load_runtime_settings
from src.providers.base import ProviderError
from src.providers.compute.batch_stub import BatchStubComputeProvider
from src.providers.compute.local import LocalComputeProvider
from src.providers.provenance import build_provider_provenance
from src.providers.queue.local import LocalQueueProvider
from src.providers.secrets.env import EnvSecretProvider


class ProviderFacadeTests(unittest.TestCase):
    """Local provider boundaries should be useful without cloud dependencies."""

    def test_local_compute_does_not_fake_completed_jobs(self) -> None:
        """Manifest-only local jobs stay planned until a runner executes."""
        compute = LocalComputeProvider()

        result = compute.submit_job({"name": "risk"})

        self.assertEqual(result.status, "PLANNED")
        self.assertEqual(result.metadata["provider"], "local")
        self.assertEqual(result.metadata["reason"], "no local runner supplied")
        self.assertNotIn("metrics", result.metadata)
        self.assertEqual(compute.get_status(result.job_id).status, "PLANNED")

    def test_local_compute_runs_callable_synchronously(self) -> None:
        """Supplying a callable makes local compute complete real work."""
        compute = LocalComputeProvider()
        seen_payloads: list[dict[str, object]] = []

        def runner(payload: object) -> dict[str, object]:
            seen_payloads.append(dict(payload))
            return {"artifact_uri": "file:///tmp/predictions.parquet"}

        result = compute.submit_job(
            {
                "name": "predict",
                "payload": {"symbol": "SPY"},
                "handler": runner,
            }
        )

        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(seen_payloads, [{"symbol": "SPY"}])
        self.assertEqual(
            result.metadata["job_spec"],
            {"name": "predict", "payload": {"symbol": "SPY"}},
        )
        self.assertEqual(
            result.metadata["result"],
            {"artifact_uri": "file:///tmp/predictions.parquet"},
        )

    def test_local_compute_records_callable_failure(self) -> None:
        """Local failures are recorded as failed jobs with clear errors."""
        compute = LocalComputeProvider()

        def runner(payload: object) -> None:
            raise RuntimeError("fixture failure")

        result = compute.submit_job({"name": "broken", "runner": runner})

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.metadata["error"]["type"], "RuntimeError")
        self.assertEqual(result.metadata["error"]["message"], "fixture failure")

    def test_batch_stub_never_claims_completed_work(self) -> None:
        """Manifest-only GPU/cloud providers queue work instead of faking results."""
        compute = BatchStubComputeProvider("vastai")

        result = compute.submit_job({"name": "train", "model": "fin-mamba"})

        self.assertEqual(result.status, "QUEUED")
        self.assertEqual(result.metadata["provider"], "vastai")
        self.assertEqual(compute.get_status(result.job_id).status, "QUEUED")

    def test_local_queue_drains_messages_once(self) -> None:
        """The local queue is an in-memory synchronous test boundary."""
        queue = LocalQueueProvider()
        handled: list[dict[str, object]] = []

        first_id = queue.publish("jobs", {"id": 1})
        second_id = queue.publish("jobs", {"id": 2})
        count = queue.consume("jobs", lambda payload: handled.append(dict(payload)))

        self.assertEqual(first_id, "local-1")
        self.assertEqual(second_id, "local-2")
        self.assertEqual(count, 2)
        self.assertEqual(handled, [{"id": 1}, {"id": 2}])
        self.assertEqual(queue.consume("jobs", lambda payload: None), 0)

    def test_env_secret_provider_uses_injected_mapping(self) -> None:
        """Secrets stay behind an environment-backed provider boundary."""
        secrets = EnvSecretProvider({"API_TOKEN": "secret-token"})

        self.assertEqual(secrets.get("API_TOKEN"), "secret-token")
        self.assertEqual(secrets.get("MISSING", "fallback"), "fallback")
        with self.assertRaisesRegex(ProviderError, "MISSING"):
            secrets.require("MISSING")

    def test_provider_provenance_records_choices_without_secrets(self) -> None:
        """Provider provenance stores choices, not credentials."""
        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(
                env=_cloud_mvp_env(),
                base_dir=Path(temp_dir),
            )

        provenance = build_provider_provenance(settings)
        serialized = repr(provenance)

        self.assertEqual(provenance["database"]["provider"], "postgres")
        self.assertEqual(provenance["storage"]["provider"], "s3")
        self.assertEqual(provenance["compute"]["provider"], "local")
        self.assertNotIn("access-key", serialized)
        self.assertNotIn("secret-key", serialized)
        self.assertNotIn("postgresql://", serialized)


def _cloud_mvp_env() -> dict[str, str]:
    return {
        "APP_ENV": "cloud",
        "DEPLOYMENT_MODE": "cloud_mvp",
        "DATABASE_URL": "postgresql://quant:secret@db.example:5432/quant",
        "OBJECT_STORAGE_BUCKET": "quant-lake",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "access-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret-key",
    }


if __name__ == "__main__":
    unittest.main()
