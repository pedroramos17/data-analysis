"""Phase 16 API endpoint coverage."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.api import handlers
from src.config.settings import load_runtime_settings
from src.providers.registry import build_provider_registry


class Phase16ApiHandlerTests(unittest.TestCase):
    """Endpoint handlers should return run IDs through orchestration."""

    def test_pipeline_run_dry_run_list_efficiency_and_reports(self) -> None:
        with TemporaryDirectory() as temp_dir:
            registry = _registry(Path(temp_dir))

            dry_run = handlers.pipeline_dry_run(registry, {"pipeline": {"tasks": ["ingest_raw"]}})
            run = handlers.pipeline_run(registry, {"sync": True, "name": "api_sync", "pipeline": {"tasks": ["ingest_raw"]}})
            runs = handlers.pipeline_runs(registry)
            efficiency = handlers.efficiency(registry, run["run_id"])
            reports = handlers.reports(registry, run["run_id"])

        self.assertEqual(dry_run["status"], "DRY_RUN")
        self.assertIsNone(dry_run["run_id"])
        self.assertIsInstance(run["run_id"], int)
        self.assertEqual(run["status"], "COMPLETED")
        self.assertFalse(run["queued"])
        self.assertGreaterEqual(runs["count"], 1)
        self.assertEqual(efficiency["run_id"], run["run_id"])
        self.assertIn("report_paths", efficiency["efficiency"])
        self.assertEqual(reports["run_id"], run["run_id"])
        self.assertIn("reports", reports)

    def test_single_stage_endpoints_queue_orchestrated_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            registry = _registry(Path(temp_dir))
            endpoints = (
                handlers.ingest_run,
                handlers.preprocess_run,
                handlers.features_build,
                handlers.windows_build,
                handlers.train_run,
                handlers.evaluate_run,
                handlers.backtest_run,
            )

            results = [endpoint(registry, {"sync": False}) for endpoint in endpoints]

        for result in results:
            self.assertIsInstance(result["run_id"], int)
            self.assertTrue(result["queued"])
            self.assertEqual(result["status"], "PLANNED")

    def test_cost_and_runpod_compute_endpoints_return_run_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            registry = _registry(Path(temp_dir), compute_provider="runpod")

            estimate = handlers.cost_estimate(registry, {"model_name": "naive_return"})
            dry_run = handlers.compute_runpod_dry_run(registry, _remote_runpod_config(), principal="api_key:test")
            cancel = handlers.compute_runpod_cancel(registry, {"job_id": dry_run["submission"]["job_id"]}, principal="api_key:test")

        self.assertEqual(estimate["recommended_option"], "local_cpu")
        self.assertIsInstance(dry_run["run_id"], int)
        self.assertEqual(dry_run["status"], "PLANNED")
        self.assertIsInstance(cancel["run_id"], int)
        self.assertEqual(cancel["status"], "CANCELLED")

    def test_api_train_endpoint_uses_orchestration_shape_not_direct_training_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            registry = _registry(Path(temp_dir))

            result = handlers.train_run(registry, {"sync": False, "model_name": "naive_return"})

        self.assertIn("run_id", result)
        self.assertIn("run", result)
        self.assertNotIn("outputs", result)


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is required for API route tests")
class Phase16FastApiRouteTests(unittest.TestCase):
    """FastAPI routes should expose docs, auth, and rate limits."""

    def test_openapi_contains_phase16_paths(self) -> None:
        from src.api.app import create_app

        with TemporaryDirectory() as temp_dir:
            app = create_app(_registry(Path(temp_dir)))

        paths = set(app.openapi()["paths"])
        for path in (
            "/health",
            "/runtime",
            "/pipeline/runs",
            "/pipeline/run",
            "/pipeline/dry-run",
            "/ingest/run",
            "/preprocess/run",
            "/features/build",
            "/windows/build",
            "/train/run",
            "/evaluate/run",
            "/backtest/run",
            "/cost/estimate",
            "/compute/runpod/dry-run",
            "/compute/runpod/submit",
            "/compute/runpod/cancel",
            "/efficiency/{run_id}",
            "/reports/{run_id}",
        ):
            self.assertIn(path, paths)

    def test_heavy_endpoints_require_auth_and_gpu_submit_is_rate_limited(self) -> None:
        from fastapi.testclient import TestClient

        from src.api.app import create_app

        with TemporaryDirectory() as temp_dir:
            registry = _registry(
                Path(temp_dir),
                compute_provider="runpod",
                extra_env={
                    "API_KEYS": "valid-key",
                    "RATE_LIMIT_GPU_SUBMIT_RPH": "2",
                    "RATE_LIMIT_GPU_SUBMIT_RPD": "10",
                },
            )
            client = TestClient(create_app(registry))

            missing_auth = client.post("/pipeline/run", json={"pipeline": {"tasks": ["ingest_raw"]}})
            first = client.post("/compute/runpod/submit", json=_remote_runpod_config(), headers={"X-API-Key": "valid-key"})
            second = client.post("/compute/runpod/submit", json=_remote_runpod_config(), headers={"X-API-Key": "valid-key"})

        self.assertEqual(missing_auth.status_code, 401)
        self.assertEqual(first.status_code, 200)
        self.assertIn("run_id", first.json())
        self.assertEqual(second.status_code, 429)


def _registry(base_dir: Path, *, compute_provider: str = "local", extra_env: dict[str, str] | None = None):
    env = {
        "DATA_LAKE_ROOT": str(base_dir / "lake"),
        "SQLITE_PATH": str(base_dir / "db.sqlite3"),
        "MODEL_CACHE_DIR": str(base_dir / "models"),
        "AUDIT_LOG_PATH": str(base_dir / "audit" / "security_audit.jsonl"),
        "COMPUTE_PROVIDER": compute_provider,
    }
    if extra_env:
        env.update(extra_env)
    settings = load_runtime_settings(env=env, base_dir=base_dir)
    return build_provider_registry(settings)


def _remote_runpod_config() -> dict[str, object]:
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
