"""Tests for provider-neutral cloud facade construction."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase


class ProviderRegistryTests(SimpleTestCase):
    """Provider registry must build local-first adapters from runtime settings."""

    def test_local_registry_builds_working_fallback_providers(self) -> None:
        """Local defaults provide storage, SQLite, queue, secrets, and compute."""
        from src.config.settings import load_runtime_settings
        from src.providers.registry import build_provider_registry

        with TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(env={}, base_dir=Path(temp_dir))
            registry = build_provider_registry(settings)
            storage = registry.get_storage()

            storage.put_bytes("sample/a.txt", b"alpha", "text/plain")

            self.assertTrue(storage.exists("sample/a.txt"))
            self.assertEqual(storage.get_bytes("sample/a.txt"), b"alpha")
            self.assertEqual(storage.list("sample"), ["sample/a.txt"])
            self.assertTrue(
                storage.presign_read("sample/a.txt", 60).startswith("file:")
            )
            self.assertTrue(registry.get_db().healthcheck())
            self.assertTrue(registry.get_queue().healthcheck())
            self.assertEqual(
                registry.get_compute().submit_job({"name": "x"}).status,
                "COMPLETED",
            )
            self.assertEqual(
                registry.get_secrets().get("MISSING", "fallback"),
                "fallback",
            )
            self.assertEqual(
                registry.get_warehouse().__class__.__name__,
                "DuckDBWarehouseProvider",
            )

    def test_local_model_registry_round_trips_metadata(self) -> None:
        """Local model registry stores metadata and resolves artifact URIs."""
        from src.config.settings import load_runtime_settings
        from src.providers.registry import build_provider_registry

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model_file = root / "model.bin"
            model_file.write_bytes(b"weights")
            settings = load_runtime_settings(env={}, base_dir=root)
            registry = build_provider_registry(settings).get_model_registry()

            saved = registry.save_model("mamba", "v1", model_file, {"seed": 17})

            self.assertEqual(saved["name"], "mamba")
            self.assertEqual(saved["version"], "v1")
            self.assertEqual(
                registry.load_model("mamba", "v1")["metadata"],
                {"seed": 17},
            )
            self.assertTrue(
                registry.resolve_artifact_uri("mamba", "v1").startswith("file:")
            )
            self.assertEqual(registry.list_models("mamba")[0]["version"], "v1")

    def test_cloud_registry_keeps_s3_sdk_inside_provider(self) -> None:
        """S3-compatible storage fails clearly when optional SDK is missing."""
        from src.config.settings import load_runtime_settings
        from src.providers.registry import build_provider_registry
        from src.providers.storage.s3_compatible import S3CompatibleStorageProvider

        settings = load_runtime_settings(env=_cloud_mvp_env(), base_dir=Path("C:/app"))
        storage = build_provider_registry(settings).get_storage()

        self.assertIsInstance(storage, S3CompatibleStorageProvider)
        with self.assertRaisesRegex(RuntimeError, "boto3.*expected installed module"):
            storage.put_bytes("x.txt", b"x")

    def test_unsupported_queue_provider_fails_clearly(self) -> None:
        """Redis provider is a boundary stub unless redis is installed."""
        from src.config.settings import load_runtime_settings
        from src.providers.registry import build_provider_registry

        settings = load_runtime_settings(
            env={"QUEUE_PROVIDER": "redis", "REDIS_URL": "redis://localhost:6379/0"},
            base_dir=Path("C:/app"),
        )

        with self.assertRaisesRegex(RuntimeError, "redis.*expected installed module"):
            build_provider_registry(settings).get_queue().healthcheck()


def _cloud_mvp_env() -> dict[str, str]:
    return {
        "APP_ENV": "cloud",
        "DEPLOYMENT_MODE": "cloud_mvp",
        "DATABASE_URL": "postgresql://quant:secret@db.example:5432/quant",
        "OBJECT_STORAGE_BUCKET": "quant-lake",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "access-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret-key",
    }
