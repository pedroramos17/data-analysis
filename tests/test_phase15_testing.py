"""Phase 15 test coverage and budget-safety gates."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from src.config.settings import (
    DatabaseSettings,
    StorageSettings,
    load_runtime_settings,
)
from src.features.definitions import feature_names
from src.features.sql import feature_store_sql
from src.models.base import MissingModelDependencyError
from src.models.registry import build_default_model_registry
from src.models.sequence._torch import torch_modules
from src.models.sequence.fin_mamba import FinMambaBlock, FinMambaConfig
from src.models.sequence.samba_block import SambaConfig, SambaForecastModel
from src.providers.base import MissingProviderDependencyError, ProviderError
from src.providers.database.postgres import PostgresDatabaseProvider
from src.providers.database.sqlite import SqliteDatabaseProvider
from src.providers.model_registry.local import LocalModelRegistryProvider
from src.providers.registry import build_provider_registry
from src.providers.storage.local import LocalStorageProvider
from src.providers.storage.s3_compatible import S3CompatibleStorageProvider
from src.providers.warehouse.duckdb_provider import DuckDBWarehouseProvider
from src.warehouse.materialize import research_panel_sql
from src.workflows.mvp_demo import MvpDemoConfig, run_mvp_demo

HAVE_LOCAL_MVP_DEPS = all(
    importlib.util.find_spec(name) for name in ("sqlalchemy", "duckdb", "pyarrow")
)


class Phase15UnitTests(unittest.TestCase):
    """Dependency-light unit coverage for local-first provider boundaries."""

    def test_settings_parsing_local_and_cloud_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local = load_runtime_settings(env={}, base_dir=root)
            cloud = load_runtime_settings(
                env={
                    "APP_ENV": "cloud",
                    "DEPLOYMENT_MODE": "cloud_mvp",
                    "DATABASE_URL": "postgresql://quant:secret@db:5432/quant",
                    "STORAGE_PROVIDER": "minio",
                    "OBJECT_STORAGE_BUCKET": "quant-lake",
                    "OBJECT_STORAGE_ACCESS_KEY_ID": "access-key",
                    "OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret-key",
                    "OBJECT_STORAGE_ENDPOINT_URL": "http://127.0.0.1:9000",
                    "CLOUD_MONTHLY_BUDGET_USD": "12.5",
                    "CLOUD_REQUIRE_BUDGET_APPROVAL": "true",
                },
                base_dir=root,
            )

        self.assertEqual(local.database.db_mode, "sqlite")
        self.assertEqual(local.storage.provider, "local")
        self.assertEqual(cloud.database.db_mode, "postgres")
        self.assertEqual(cloud.storage.provider, "minio")
        self.assertEqual(cloud.cost.monthly_budget_usd, 12.5)
        self.assertTrue(cloud.cost.require_budget_approval)

    def test_provider_registry_resolves_local_providers_without_cloud_sdks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(env={}, base_dir=Path(temp_dir))
            registry = build_provider_registry(settings)

            storage = registry.get_storage()
            database = registry.get_db()
            model_registry = registry.get_model_registry()

        self.assertIsInstance(storage, LocalStorageProvider)
        self.assertIsInstance(database, SqliteDatabaseProvider)
        self.assertIsInstance(model_registry, LocalModelRegistryProvider)
        self.assertEqual(registry.get_compute().submit_job({"name": "x"}).status, "PLANNED")

    def test_local_storage_round_trip_listing_presign_and_path_safety(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = LocalStorageProvider(Path(temp_dir))
            uri = storage.put_bytes("phase15/object.txt", b"ok", "text/plain")

            self.assertEqual(storage.get_bytes("phase15/object.txt"), b"ok")
            self.assertEqual(storage.list("phase15"), ["phase15/object.txt"])
            self.assertEqual(storage.presign_read("phase15/object.txt", 60), uri)
            with self.assertRaises(ProviderError):
                storage.put_bytes("../escape.txt", b"bad")

    def test_sqlite_provider_healthcheck_and_migration_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(env={}, base_dir=Path(temp_dir))
            provider = SqliteDatabaseProvider(settings.database)

            self.assertTrue(provider.healthcheck())
            self.assertEqual(
                provider.run_migrations(),
                {"status": "managed_by_django", "provider": "sqlite"},
            )

    def test_postgres_provider_optional_dependency_boundary(self) -> None:
        settings = DatabaseSettings(
            "postgres",
            Path("unused.sqlite3"),
            "postgresql://quant:secret@db.example:5432/quant",
        )
        provider = PostgresDatabaseProvider(settings)

        self.assertEqual(provider.run_migrations()["provider"], "postgres")
        if importlib.util.find_spec("psycopg") is None:
            with self.assertRaises(MissingProviderDependencyError):
                provider.get_engine()

    def test_duckdb_query_provider_executes_or_fails_lazily(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(env={}, base_dir=Path(temp_dir))
            provider = DuckDBWarehouseProvider(settings.duckdb)

            if importlib.util.find_spec("duckdb") is None:
                with self.assertRaises(MissingProviderDependencyError):
                    provider.query("select 1 as value")
            else:
                self.assertEqual(provider.query("select 1 as value"), [{"value": 1}])

        sql = research_panel_sql(["SPY"], "2024-01-01", "2024-01-02", "1d")
        self.assertIn("from v_signal_panel", sql)
        self.assertIn("upper(symbol) in ('SPY')", sql)

    def test_model_registry_factories_and_local_artifact_provider(self) -> None:
        registry = build_default_model_registry()
        self.assertIn("naive_return", registry.names())
        self.assertIn("samba", registry.names())

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact.json"
            artifact.write_text('{"ok": true}', encoding="utf-8")
            provider = LocalModelRegistryProvider(root / "models")

            saved = provider.save_model("phase15", "v1", artifact, {"metric": 1})
            loaded = provider.load_model("phase15", "v1")
            artifact_uri = provider.resolve_artifact_uri("phase15", "v1")

        self.assertEqual(saved["name"], "phase15")
        self.assertEqual(loaded["metadata"], {"metric": 1})
        self.assertTrue(artifact_uri.startswith("file:"))

    def test_feature_calculation_sql_contract(self) -> None:
        sql = feature_store_sql(
            version="phase15_v1",
            groups=("price_volume", "risk", "portfolio"),
            universe=("SPY",),
            start="2024-01-01",
            end="2024-01-31",
            timeframe="1d",
        )

        names = set(feature_names())
        self.assertIn("rolling_volatility", names)
        self.assertIn("turnover_constraints", names)
        self.assertIn("close / nullif(previous_close, 0) - 1.0", sql)
        self.assertIn("stddev_samp(log_returns)", sql)
        self.assertIn("'phase15_v1' as version", sql)

    def test_fin_mamba_forward_pass_when_torch_available(self) -> None:
        torch = _torch_or_skip(self, "Fin-Mamba Phase 15 forward pass")
        config = FinMambaConfig(
            input_dim=3,
            hidden_dim=6,
            num_layers=1,
            horizon=2,
            dropout=0.0,
            asset_conditioning=False,
            use_regime_features=False,
            use_graph_features=False,
        )
        model = FinMambaBlock(config).build()

        output = model(torch.randn(2, 5, 3), return_diagnostics=True)

        self.assertEqual(output["predictions"]["return_forecast"].shape, (2, 2))
        self.assertIn("latent_state_summary", output["diagnostics"])

    def test_samba_forward_pass_when_torch_available(self) -> None:
        torch = _torch_or_skip(self, "SAMBA Phase 15 forward pass")
        model = SambaForecastModel(SambaConfig(input_dim=3, hidden_dim=6, horizon=2))
        module = model.build()

        output = module(torch.randn(2, 5, 3), return_diagnostics=True)

        self.assertEqual(output["forecast"].shape, (2, 2, 1))
        self.assertIn("branch_diagnostics", output)


@unittest.skipUnless(
    HAVE_LOCAL_MVP_DEPS,
    "SQLAlchemy, DuckDB, and PyArrow are required for local MVP integration",
)
class Phase15LocalIntegrationTests(unittest.TestCase):
    """Local integration tests that never use paid cloud services."""

    def test_local_full_mvp_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            lake_root = root / "lake"
            config = MvpDemoConfig(
                run_id="phase15_local",
                symbols=("SPY",),
                periods=6,
                lake_root=lake_root,
                duckdb_path=lake_root / "analytics.duckdb",
                database_url=f"sqlite:///{(root / 'mvp.sqlite3').as_posix()}",
                optional_sequence_models=(),
            )

            with _local_env(root):
                result = run_mvp_demo(config)

            self.assertEqual(result.status, "COMPLETED")
            self.assertTrue((lake_root / result.report_path).exists())


class Phase15SmokeTests(unittest.TestCase):
    """Smoke tests should validate commands without executing heavy services."""

    def test_make_smoke_test_dry_run(self) -> None:
        result = _run_make_dry_run("smoke-test")

        self.assertIn("APP_ENV=local", result.stdout)
        self.assertIn("python3 -m src.cli config show", result.stdout)
        self.assertIn("python3 -m src.cli smoke-test", result.stdout)
        self.assertNotIn("RUNPOD_API_KEY", result.stdout)

    def test_make_mvp_demo_dry_run(self) -> None:
        result = _run_make_dry_run("mvp-demo")

        self.assertIn("python3 -m src.cli mvp-demo", result.stdout)
        self.assertIn("configs/cloud_mvp.yaml", result.stdout)

    def test_docker_compose_postgres_config_when_docker_available(self) -> None:
        if shutil.which("docker") is None:
            self.skipTest("docker is not installed")

        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.postgres.yml", "config"],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("postgres", result.stdout)


class Phase15CloudGatedIntegrationTests(unittest.TestCase):
    """Potential cloud/object-store calls require ENABLE_CLOUD_TESTS=true."""

    def test_cloud_tests_are_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(_cloud_tests_enabled())

    def test_postgres_provider_healthcheck_when_explicitly_enabled(self) -> None:
        if not _cloud_tests_enabled():
            self.skipTest("set ENABLE_CLOUD_TESTS=true to run Postgres connectivity")
        database_url = os.environ.get("POSTGRES_TEST_DATABASE_URL", "")
        if not database_url:
            self.skipTest("POSTGRES_TEST_DATABASE_URL is not set")
        if importlib.util.find_spec("psycopg") is None:
            self.skipTest("psycopg is not installed")

        provider = PostgresDatabaseProvider(
            DatabaseSettings("postgres", Path("unused.sqlite3"), database_url)
        )

        self.assertTrue(provider.healthcheck())

    def test_minio_object_storage_round_trip_when_explicitly_enabled(self) -> None:
        if not _cloud_tests_enabled():
            self.skipTest("set ENABLE_CLOUD_TESTS=true to run object storage tests")
        if importlib.util.find_spec("boto3") is None:
            self.skipTest("boto3 is not installed")
        settings = _minio_settings_or_skip(self)
        provider = S3CompatibleStorageProvider(settings)
        key = f"phase15/{uuid.uuid4().hex}.txt"

        try:
            uri = provider.put_bytes(key, b"phase15", "text/plain")
            self.assertEqual(provider.get_bytes(key), b"phase15")
            self.assertIn(key, provider.list("phase15/"))
            self.assertTrue(uri.startswith("minio://"))
        finally:
            provider.delete(key)


def _run_make_dry_run(target: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("make") is None:
        raise unittest.SkipTest("make is not installed")
    result = subprocess.run(
        ["make", "-n", target],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result


def _torch_or_skip(testcase: unittest.TestCase, feature_name: str) -> object:
    try:
        torch, _nn = torch_modules(feature_name)
    except MissingModelDependencyError as exc:
        testcase.skipTest(str(exc))
    return torch


def _cloud_tests_enabled() -> bool:
    return os.environ.get("ENABLE_CLOUD_TESTS", "").strip().lower() == "true"


def _minio_settings_or_skip(testcase: unittest.TestCase) -> StorageSettings:
    endpoint = os.environ.get("OBJECT_STORAGE_ENDPOINT_URL", "")
    bucket = os.environ.get("OBJECT_STORAGE_BUCKET", "")
    access_key = os.environ.get("OBJECT_STORAGE_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("OBJECT_STORAGE_SECRET_ACCESS_KEY", "")
    if not all((endpoint, bucket, access_key, secret_key)):
        testcase.skipTest(
            "OBJECT_STORAGE_ENDPOINT_URL, OBJECT_STORAGE_BUCKET, and credentials "
            "are required for MinIO/object storage integration"
        )
    return StorageSettings(
        "minio",
        Path("data/lake"),
        bucket_name=bucket,
        endpoint_url=endpoint,
        access_key_id=access_key,
        secret_access_key=secret_key,
        region_name=os.environ.get("OBJECT_STORAGE_REGION", "us-east-1"),
    )


def _local_env(base_dir: Path):
    return patch.dict(
        os.environ,
        {
            "APP_ENV": "local",
            "DEPLOYMENT_MODE": "onprem",
            "DB_MODE": "sqlite",
            "SQLITE_PATH": str(base_dir / "db.sqlite3"),
            "DATA_LAKE_ROOT": str(base_dir / "lake"),
            "DUCKDB_PATH": str(base_dir / "lake" / "analytics.duckdb"),
            "STORAGE_PROVIDER": "local",
            "QUEUE_PROVIDER": "local",
            "MODEL_PROVIDER": "local",
            "MODEL_CACHE_DIR": str(base_dir / "models"),
            "COMPUTE_PROVIDER": "local",
        },
        clear=True,
    )


if __name__ == "__main__":
    unittest.main()
