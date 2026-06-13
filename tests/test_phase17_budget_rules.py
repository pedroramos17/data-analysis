"""Phase 17 budget-first architecture rule enforcement."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config.settings import (
    COMPUTE_PROVIDERS,
    DB_MODES,
    QUEUE_PROVIDERS,
    STORAGE_PROVIDERS,
    load_runtime_settings,
)

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_MVP_TOKENS = (
    "kafka",
    "spark",
    "kubernetes",
    "k8s",
    "vector-db",
    "vectordb",
    "weaviate",
    "pinecone",
    "qdrant",
    "milvus",
    "nvidia",
)
ALLOWED_CLOUD_SERVICES = {"app", "postgres", "minio", "redis", "scheduler"}
ALLOWED_LOCAL_SERVICES = {"app", "postgres", "minio", "redis"}


class BudgetFirstArchitectureRuleTests(unittest.TestCase):
    """MVP infrastructure should stay cheap and upgradeable."""

    def test_runtime_defaults_are_local_cpu_and_cheap(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = load_runtime_settings(env={}, base_dir=ROOT)

        self.assertEqual(settings.database.db_mode, "sqlite")
        self.assertEqual(settings.storage.provider, "local")
        self.assertEqual(settings.duckdb.olap_mode, "duckdb")
        self.assertEqual(settings.queue.provider, "local")
        self.assertEqual(settings.model.provider, "local")
        self.assertEqual(settings.compute.provider, "local")
        self.assertEqual(settings.pipeline.orchestrator, "local")
        self.assertEqual(settings.rate_limit.provider, "memory")
        self.assertEqual(settings.pipeline.model_device, "cpu")
        self.assertEqual(settings.pipeline.cost_mode, "minimum")
        self.assertFalse(settings.compute.gpu_required)
        self.assertFalse(settings.compute.gpu_batch_enabled)
        self.assertFalse(settings.pipeline.external_paid_api_calls_enabled)
        self.assertFalse(settings.pipeline.cloud_tests_enabled)
        self.assertLessEqual(settings.cost.monthly_budget_usd, 25.0)
        self.assertLessEqual(settings.cost.max_job_cost_usd, 2.5)
        self.assertTrue(settings.cost.require_budget_approval)

    def test_provider_enums_support_future_upgrade_path_without_heavy_mvp_defaults(self) -> None:
        self.assertEqual(set(DB_MODES), {"sqlite", "postgres"})
        self.assertGreaterEqual(set(STORAGE_PROVIDERS), {"local", "minio", "s3", "r2", "b2"})
        self.assertEqual(set(QUEUE_PROVIDERS), {"local", "redis"})
        self.assertGreaterEqual(set(COMPUTE_PROVIDERS), {"local", "runpod", "colab", "vastai", "stub"})

        forbidden_providers = {"kafka", "spark", "kubernetes", "k8s", "gpu_always_on"}
        all_provider_values = set(DB_MODES) | set(STORAGE_PROVIDERS) | set(QUEUE_PROVIDERS) | set(COMPUTE_PROVIDERS)
        self.assertFalse(forbidden_providers & all_provider_values)

    def test_docker_compose_stacks_only_define_cheap_mvp_services(self) -> None:
        local_services = _compose_services(ROOT / "docker-compose.local.yml")
        cloud_services = _compose_services(ROOT / "docker-compose.cloud-mvp.yml")

        self.assertLessEqual(local_services, ALLOWED_LOCAL_SERVICES)
        self.assertLessEqual(cloud_services, ALLOWED_CLOUD_SERVICES)
        self.assertEqual(cloud_services, ALLOWED_CLOUD_SERVICES)
        self.assertNotIn("kafka", cloud_services)
        self.assertNotIn("spark", cloud_services)

    def test_compose_files_do_not_require_forbidden_or_always_on_gpu_infra(self) -> None:
        for path in (ROOT / "docker-compose.local.yml", ROOT / "docker-compose.cloud-mvp.yml"):
            text = _without_comments(path.read_text(encoding="utf-8").lower())
            for token in FORBIDDEN_MVP_TOKENS:
                self.assertNotIn(token, text, f"{token} should not be required in {path.name}")
            self.assertNotIn("deploy:", text)
            self.assertNotIn("devices:", text)
            self.assertNotIn("gpu", text)

    def test_env_examples_keep_gpu_and_expensive_stack_disabled_by_default(self) -> None:
        local_env = (ROOT / ".env.example").read_text(encoding="utf-8")
        cloud_env = (ROOT / ".env.cloud.example").read_text(encoding="utf-8")

        self.assertIn("DB_MODE=sqlite", local_env)
        self.assertIn("STORAGE_PROVIDER=local", local_env)
        self.assertIn("DB_MODE=postgres", cloud_env)
        self.assertIn("STORAGE_PROVIDER=minio", cloud_env)
        for text in (local_env, cloud_env):
            self.assertIn("OLAP_MODE=duckdb", text)
            self.assertIn("GPU_REQUIRED=false", text)
            self.assertIn("GPU_BATCH_ENABLED=false", text)
            self.assertIn("ORCHESTRATOR=local", text)
            self.assertIn("RATE_LIMIT_PROVIDER=memory", text)
            self.assertIn("MODEL_DEVICE=cpu", text)
            self.assertIn("COST_MODE=minimum", text)
            self.assertIn("ENABLE_CLOUD_TESTS=false", text)
            self.assertIn("ALLOW_EXTERNAL_PAID_API_CALLS=false", text)
            self.assertIn("CLOUD_REQUIRE_BUDGET_APPROVAL=true", text)

    def test_budget_first_documentation_captures_rules_and_upgrade_path(self) -> None:
        text = (ROOT / "docs" / "architecture" / "budget_first_rules.md").read_text(
            encoding="utf-8"
        )

        for required in (
            "one cheap VPS or free-tier VM",
            "Docker Compose",
            "embedded DuckDB",
            "S3-compatible storage",
            "CPU inference by default",
            "optional only for batch training jobs",
            "Kubernetes",
            "Kafka",
            "Spark",
            "managed vector database",
            "always-on GPU",
            "Redis, RabbitMQ, or SQS",
            "MotherDuck, BigQuery, or Snowflake",
            "Airflow, Prefect, or Dagster",
            "SQLite | retained for edge, on-premise, and offline mode",
        ):
            self.assertIn(required, text)

    def test_readme_links_budget_first_rules(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("Budget-first architecture rules", readme)
        self.assertIn("docs/architecture/budget_first_rules.md", readme)


def _compose_services(path: Path) -> set[str]:
    services: set[str] = set()
    in_services = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("services:"):
            in_services = True
            continue
        if in_services and line.startswith("volumes:"):
            break
        if in_services and line.startswith("  ") and not line.startswith("    "):
            name = line.strip().rstrip(":")
            if name:
                services.add(name)
    return services


def _without_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    unittest.main()
