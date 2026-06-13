"""Tests for hybrid quant runtime environment settings."""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


class RuntimeSettingsTests(SimpleTestCase):
    """Runtime settings must keep local mode cheap and cloud mode explicit."""

    def test_local_defaults_require_no_cloud_credentials(self) -> None:
        """Local settings use SQLite, local storage, DuckDB file, and CPU compute."""
        from src.config.settings import load_runtime_settings

        base_dir = Path("C:/workspace/data-analysis")

        result = load_runtime_settings(env={}, base_dir=base_dir)

        self.assertEqual(result.app_env, "local")
        self.assertEqual(result.deployment_mode, "onprem")
        self.assertEqual(result.database.db_mode, "sqlite")
        self.assertEqual(
            result.database.as_django_database()["NAME"],
            base_dir / "db.sqlite3",
        )
        self.assertEqual(result.storage.provider, "local")
        self.assertEqual(result.storage.local_root, base_dir / "data" / "lake")
        self.assertEqual(
            result.duckdb.database_path,
            base_dir / "data" / "lake" / "analytics.duckdb",
        )
        self.assertEqual(result.queue.provider, "local")
        self.assertEqual(result.secrets_provider, "env")
        self.assertEqual(result.model.cache_root, base_dir / "models")
        self.assertEqual(result.compute.provider, "local")
        self.assertFalse(result.compute.gpu_required)
        self.assertEqual(result.pipeline.orchestrator, "local")
        self.assertEqual(result.pipeline.model_device, "cpu")
        self.assertEqual(result.pipeline.cost_mode, "minimum")
        self.assertEqual(result.rate_limit.provider, "memory")
        self.assertFalse(result.cost.external_paid_api_calls_enabled)
        self.assertFalse(result.cost.cloud_tests_enabled)

    def test_sqlite_database_profile_ignores_database_url(self) -> None:
        """SQLite remains default even when a cloud URL is present in env files."""
        from src.config.settings import load_runtime_settings

        base_dir = Path("/workspace/data-analysis")

        result = load_runtime_settings(
            env={"DATABASE_URL": "postgresql://quant:secret@db.example:5432/quant"},
            base_dir=base_dir,
        )

        database = result.database.as_django_database()
        self.assertEqual(result.database.db_mode, "sqlite")
        self.assertEqual(database["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(database["NAME"], base_dir / "db.sqlite3")

    def test_cloud_mvp_defaults_to_postgres_and_s3_storage(self) -> None:
        """Cloud MVP settings accept Postgres and S3-compatible credentials."""
        from src.config.settings import load_runtime_settings

        result = load_runtime_settings(env=_cloud_mvp_env(), base_dir=Path("C:/app"))

        database = result.database.as_django_database()
        self.assertEqual(result.app_env, "cloud")
        self.assertEqual(result.deployment_mode, "cloud_mvp")
        self.assertEqual(result.database.db_mode, "postgres")
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["NAME"], "quant")
        self.assertEqual(database["USER"], "quant_user")
        self.assertEqual(database["HOST"], "db.example.internal")
        self.assertEqual(result.storage.provider, "s3")
        self.assertEqual(result.storage.bucket_name, "quant-lake")
        self.assertEqual(
            result.storage.endpoint_url,
            "https://storage.example.internal",
        )
        self.assertEqual(result.queue.provider, "local")
        self.assertEqual(result.compute.provider, "local")
        self.assertFalse(result.compute.gpu_required)

    def test_postgres_profile_renders_from_database_url(self) -> None:
        """Postgres mode can render a Django database config from DATABASE_URL."""
        from src.config.settings import load_runtime_settings

        result = load_runtime_settings(
            env={
                "DB_MODE": "postgres",
                "DATABASE_URL": (
                    "postgres://quant_user:p%40ss@db.example.internal:6543/"
                    "quant?sslmode=require"
                ),
            },
            base_dir=Path("/workspace/data-analysis"),
        )

        database = result.database.as_django_database()
        self.assertEqual(result.database.db_mode, "postgres")
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["NAME"], "quant")
        self.assertEqual(database["USER"], "quant_user")
        self.assertEqual(database["PASSWORD"], "p@ss")
        self.assertEqual(database["HOST"], "db.example.internal")
        self.assertEqual(database["PORT"], "6543")
        self.assertEqual(database["OPTIONS"], {"sslmode": "require"})

    def test_postgres_profile_renders_from_component_env(self) -> None:
        """Postgres mode also accepts split environment variables."""
        from src.config.settings import load_runtime_settings

        result = load_runtime_settings(
            env={
                "DB_MODE": "postgres",
                "POSTGRES_DB": "quant",
                "POSTGRES_USER": "quant_user",
                "POSTGRES_PASSWORD": "p@ss word",
                "POSTGRES_HOST": "db.example.internal",
                "POSTGRES_PORT": "6543",
                "POSTGRES_SSLMODE": "require",
            },
            base_dir=Path("/workspace/data-analysis"),
        )

        database = result.database.as_django_database()
        self.assertTrue(result.database.postgres_url.startswith("postgresql://"))
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["NAME"], "quant")
        self.assertEqual(database["USER"], "quant_user")
        self.assertEqual(database["PASSWORD"], "p@ss word")
        self.assertEqual(database["HOST"], "db.example.internal")
        self.assertEqual(database["PORT"], "6543")
        self.assertEqual(database["OPTIONS"], {"sslmode": "require"})

    def test_postgres_profile_requires_url_or_components(self) -> None:
        """Postgres mode fails before Django starts with incomplete settings."""
        from src.config.settings import load_runtime_settings

        with self.assertRaisesRegex(ValueError, "DATABASE_URL or POSTGRES_DB"):
            load_runtime_settings(
                env={"DB_MODE": "postgres"},
                base_dir=Path("/workspace/data-analysis"),
            )

    def test_all_providers_can_be_overridden_for_tests(self) -> None:
        """Tests can inject every provider choice without mutating process env."""
        from src.config.settings import load_runtime_settings

        env = _cloud_mvp_env() | {
            "APP_ENV": "test",
            "DEPLOYMENT_MODE": "cloud_gpu",
            "STORAGE_PROVIDER": "r2",
            "QUEUE_PROVIDER": "redis",
            "REDIS_URL": "redis://localhost:6379/0",
            "SECRETS_PROVIDER": "doppler",
            "MODEL_PROVIDER": "huggingface",
            "COMPUTE_PROVIDER": "runpod",
            "ORCHESTRATOR": "prefect",
            "RATE_LIMIT_PROVIDER": "redis",
            "MODEL_DEVICE": "cuda",
            "COST_MODE": "balanced",
            "GPU_REQUIRED": "true",
            "RUNPOD_API_KEY": "runpod-secret",
            "RUNPOD_GPU_TYPE": "NVIDIA L4",
            "CLOUD_MONTHLY_BUDGET_USD": "42.50",
            "CLOUD_MAX_JOB_COST_USD": "3.25",
        }

        result = load_runtime_settings(env=env, base_dir=Path("C:/app"))

        self.assertEqual(result.app_env, "test")
        self.assertEqual(result.deployment_mode, "cloud_gpu")
        self.assertEqual(result.storage.provider, "r2")
        self.assertEqual(result.queue.provider, "redis")
        self.assertEqual(result.queue.connection_url, "redis://localhost:6379/0")
        self.assertEqual(result.secrets_provider, "doppler")
        self.assertEqual(result.model.provider, "huggingface")
        self.assertEqual(result.compute.provider, "runpod")
        self.assertEqual(result.pipeline.orchestrator, "prefect")
        self.assertEqual(result.rate_limit.provider, "redis")
        self.assertEqual(result.pipeline.model_device, "cuda")
        self.assertEqual(result.cost.cost_mode, "balanced")
        self.assertEqual(result.runpod.gpu_type, "NVIDIA L4")
        self.assertTrue(result.compute.gpu_required)
        self.assertEqual(result.cost.monthly_budget_usd, 42.50)
        self.assertEqual(result.cost.max_job_cost_usd, 3.25)

    def test_cloud_gpu_defaults_are_dry_run_and_do_not_require_credentials(self) -> None:
        """RunPod cloud-GPU mode can plan manifests without paid infrastructure."""
        from src.config.settings import load_runtime_settings

        result = load_runtime_settings(
            env={"APP_ENV": "cloud", "DEPLOYMENT_MODE": "cloud_gpu"},
            base_dir=Path("/workspace/data-analysis"),
        )

        self.assertEqual(result.deployment_mode, "cloud_gpu")
        self.assertEqual(result.database.db_mode, "sqlite")
        self.assertEqual(result.storage.provider, "local")
        self.assertEqual(result.compute.provider, "runpod")
        self.assertTrue(result.runpod.dry_run)
        self.assertTrue(result.runpod.terminate_on_completion)
        self.assertEqual(result.pipeline.model_device, "cpu")
        self.assertFalse(result.pipeline.cloud_tests_enabled)

    def test_invalid_provider_reports_expected_values(self) -> None:
        """Invalid provider names fail with offending value and expected shape."""
        from src.config.settings import load_runtime_settings

        with self.assertRaisesRegex(ValueError, "celery.*expected one of"):
            load_runtime_settings(
                env={"QUEUE_PROVIDER": "celery"},
                base_dir=Path("C:/app"),
            )


def _cloud_mvp_env() -> dict[str, str]:
    return {
        "APP_ENV": "cloud",
        "DEPLOYMENT_MODE": "cloud_mvp",
        "DATABASE_URL": (
            "postgresql://quant_user:secret@db.example.internal:5432/"
            "quant?sslmode=require"
        ),
        "OBJECT_STORAGE_BUCKET": "quant-lake",
        "OBJECT_STORAGE_ENDPOINT_URL": "https://storage.example.internal",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "access-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret-key",
    }
