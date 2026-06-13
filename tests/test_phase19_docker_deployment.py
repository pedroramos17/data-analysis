"""Phase 19 Docker and deployment checks."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Phase19DockerDeploymentTests(unittest.TestCase):
    def test_required_deployment_files_exist(self) -> None:
        for relative in (
            "Dockerfile",
            "Dockerfile.gpu",
            "docker-compose.local.yml",
            "docker-compose.cloud.yml",
            "docker-compose.cloud-mvp.yml",
            ".env.example",
            ".env.runpod.example",
            "infra/scheduler_loop.py",
            "Makefile",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).exists(), f"missing {relative}")

    def test_local_compose_has_app_and_optional_services(self) -> None:
        compose = (ROOT / "docker-compose.local.yml").read_text(encoding="utf-8")
        services = _compose_services(compose)

        self.assertEqual(services, {"app", "postgres", "minio", "redis"})
        self.assertIn('profiles: ["postgres"]', compose)
        self.assertIn('profiles: ["minio"]', compose)
        self.assertIn('profiles: ["redis"]', compose)
        self.assertIn("COMPUTE_PROVIDER: ${COMPUTE_PROVIDER:-local}", compose)

    def test_cloud_compose_keeps_runpod_as_external_job_provider(self) -> None:
        compose = (ROOT / "docker-compose.cloud.yml").read_text(encoding="utf-8")
        services = _compose_services(compose)

        self.assertEqual(services, {"app", "postgres", "minio", "redis"})
        self.assertIn("RUNPOD_DRY_RUN: ${RUNPOD_DRY_RUN:-true}", compose)
        self.assertNotIn("runpod:", compose)
        self.assertNotIn("devices:", compose)
        self.assertNotIn("nvidia", _without_comments(compose).lower())

    def test_gpu_dockerfile_uses_cuda_runtime_without_baked_secrets(self) -> None:
        text = (ROOT / "Dockerfile.gpu").read_text(encoding="utf-8")

        self.assertIn("FROM pytorch/pytorch:", text)
        self.assertIn("cuda", text.lower())
        self.assertIn("RUNPOD_DRY_RUN=true", text)
        self.assertIn("python -m pip install -e . --no-deps", text)
        self.assertNotIn("RUNPOD_API_KEY=", text)
        self.assertNotIn("OBJECT_STORAGE_SECRET_ACCESS_KEY=", text)

    def test_runpod_entrypoint_validates_uploads_and_exits_cleanly(self) -> None:
        text = (ROOT / "infra" / "runpod" / "entrypoint_train.sh").read_text(encoding="utf-8")

        self.assertIn("validate_config", text)
        self.assertIn("python3 -m src.cli cost estimate --config", text)
        self.assertIn("validate_command", text)
        self.assertIn("run_command", text)
        self.assertIn("upload_one", text)
        self.assertNotIn("shutil.rmtree", text)
        self.assertIn("RUNPOD_LOGS_URI", text)
        self.assertIn("RUNPOD_ARTIFACTS_URI", text)
        self.assertIn("trap cleanup EXIT", text)
        self.assertIn("trap term_handler INT TERM", text)
        self.assertIn("exit 143", text)

    def test_runpod_entrypoints_use_python3_cli_commands(self) -> None:
        for relative in ("entrypoint_train.sh", "entrypoint_infer.sh"):
            with self.subTest(relative=relative):
                text = (ROOT / "infra" / "runpod" / relative).read_text(encoding="utf-8")
                self.assertIn("python3 -m src.cli", text)
                self.assertNotIn("python -m src.cli", text)
                self.assertNotIn("python -", text)
                self.assertNotIn("sh -c", text)
                self.assertIn("shlex.split", text)
                self.assertIn("subprocess.run", text)

    def test_cloud_mvp_scheduler_uses_shell_free_loop(self) -> None:
        compose = (ROOT / "docker-compose.cloud-mvp.yml").read_text(encoding="utf-8")
        scheduler = (ROOT / "infra" / "scheduler_loop.py").read_text(encoding="utf-8")

        self.assertIn('["python3", "infra/scheduler_loop.py"]', compose)
        self.assertNotIn("sh -c", compose)
        self.assertIn("shell=False", scheduler)
        self.assertIn("subprocess.run", scheduler)

    def test_cloud_compose_passwords_come_from_env_file(self) -> None:
        for relative in ("docker-compose.cloud.yml", "docker-compose.cloud-mvp.yml"):
            with self.subTest(relative=relative):
                compose = (ROOT / relative).read_text(encoding="utf-8")

                self.assertIn("POSTGRES_PASSWORD required", compose)
                self.assertIn("MINIO_ROOT_PASSWORD required", compose)
                self.assertNotIn("POSTGRES_PASSWORD:-", compose)
                self.assertNotIn("MINIO_ROOT_PASSWORD:-", compose)

    def test_makefile_exposes_required_targets(self) -> None:
        text = (ROOT / "Makefile").read_text(encoding="utf-8")

        for target in (
            "install:",
            "test:",
            "smoke-test:",
            "local-up:",
            "local-down:",
            "mvp-demo-local:",
            "pipeline-local:",
            "runpod-dry-run:",
            "cost-estimate:",
            "efficiency-report:",
        ):
            with self.subTest(target=target):
                self.assertIn(target, text)
        self.assertIn("docker build -f Dockerfile.gpu", text)

    def test_env_examples_keep_paid_services_disabled_for_tests(self) -> None:
        local_env = (ROOT / ".env.example").read_text(encoding="utf-8")
        runpod_env = (ROOT / ".env.runpod.example").read_text(encoding="utf-8")

        for text in (local_env, runpod_env):
            self.assertIn("RUNPOD_DRY_RUN=true", text)
            self.assertIn("ALLOW_EXTERNAL_PAID_API_CALLS=false", text)
            self.assertIn("CLOUD_REQUIRE_BUDGET_APPROVAL=true", text)
        self.assertIn("RUNPOD_API_KEY=", runpod_env)
        self.assertIn("OBJECT_STORAGE_SECRET_ACCESS_KEY=", runpod_env)

    def test_gitignore_excludes_generated_runtime_artifacts(self) -> None:
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")

        for pattern in ("data/lake/", "reports/efficiency/", "models/", "*.duckdb"):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, text)

    def test_gpu_build_command_is_documented(self) -> None:
        readme = (ROOT / "infra" / "runpod" / "README.md").read_text(encoding="utf-8")

        self.assertIn("docker build -f Dockerfile.gpu", readme)
        self.assertIn("No API keys or object", readme)


def _compose_services(text: str) -> set[str]:
    services: set[str] = set()
    in_services = False
    for line in text.splitlines():
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
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


if __name__ == "__main__":
    unittest.main()
