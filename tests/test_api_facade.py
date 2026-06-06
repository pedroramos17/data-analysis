"""Smoke tests for the provider-backed API facade."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from src.api import handlers
from src.config.settings import load_runtime_settings
from src.models.explainability import SIGNAL_EXPLANATION_FIELDS
from src.providers.registry import build_provider_registry


class ApiFacadeHandlerTests(unittest.TestCase):
    """Handlers should use providers without knowing local/cloud details."""

    def test_health_and_runtime_config_use_provider_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = _registry(Path(temp_dir))

            health = handlers.health(registry)
            runtime = handlers.runtime_config(registry)

        self.assertEqual(health["status"], "ok")
        self.assertEqual(runtime["database"]["provider"], "sqlite")
        self.assertEqual(runtime["storage"]["provider"], "local")
        self.assertEqual(runtime["compute"]["provider"], "local")

    def test_async_heavy_jobs_are_queued_or_planned(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = _registry(Path(temp_dir))

            features = handlers.features_build(
                registry,
                {"version": "api_v1", "sync": False},
            )
            backtest = handlers.backtest_run(registry, {"name": "smoke"})
            risk = handlers.risk_run(registry, {"name": "smoke"})

        self.assertTrue(features["queued"])
        self.assertEqual(features["status"], "PLANNED")
        self.assertTrue(backtest["queued"])
        self.assertTrue(risk["queued"])

    def test_sync_small_model_train_and_predict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = _registry(Path(temp_dir))
            dataset = [
                {"symbol": "SPY", "ts": "2024-01-01", "log_return": 0.01},
                {"symbol": "SPY", "ts": "2024-01-02", "log_return": 0.02},
            ]

            train = handlers.models_train(
                registry,
                {"sync": True, "model_name": "naive_return", "dataset": dataset},
            )
            predict = handlers.models_predict(
                registry,
                {
                    "sync": True,
                    "model_name": "naive_return",
                    "train_dataset": dataset,
                    "dataset": [{"symbol": "SPY", "ts": "2024-01-03"}],
                    "horizon": "1d",
                    "feature_set_version": "api_features_v1",
                },
            )

        self.assertEqual(train["status"], "COMPLETED")
        self.assertEqual(train["metadata"]["result"]["model"]["model_name"], "naive_return_baseline")
        self.assertEqual(predict["status"], "COMPLETED")
        prediction = predict["metadata"]["result"]["predictions"][0]
        self.assertEqual(prediction["symbol"], "SPY")
        self.assertEqual(prediction["prediction"], 0.02)
        for field in SIGNAL_EXPLANATION_FIELDS:
            self.assertIn(field, prediction["explanation_json"])
        self.assertEqual(
            prediction["explanation_json"]["feature_set_version"],
            "api_features_v1",
        )

    def test_models_assets_signals_and_presign_endpoints_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = _registry(root)
            registry.get_storage().put_bytes("reports/smoke.txt", b"ok")

            models = handlers.models(registry)
            assets = handlers.assets(registry)
            signals = handlers.signals(registry)
            backtest = handlers.backtest(registry, 1)
            risk = handlers.risk(registry, 1)
            presign = handlers.storage_presign(registry, "reports/smoke.txt", 60)

        self.assertIn("naive_return", models["factories"])
        self.assertIn("items", assets)
        self.assertIn("items", signals)
        self.assertIn("items", backtest)
        self.assertIn("items", risk)
        self.assertTrue(str(presign["url"]).startswith("file:"))


@unittest.skipUnless(
    importlib.util.find_spec("fastapi"),
    "FastAPI is required for OpenAPI smoke tests",
)
class ApiFacadeFastApiTests(unittest.TestCase):
    """FastAPI app should expose OpenAPI paths when installed."""

    def test_openapi_contains_required_paths(self) -> None:
        from src.api.app import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(_registry(Path(temp_dir)))

        schema = app.openapi()
        paths = set(schema["paths"])

        for path in (
            "/health",
            "/config/runtime",
            "/ingest/run",
            "/features/build",
            "/models/train",
            "/models/predict",
            "/backtest/run",
            "/risk/run",
            "/assets",
            "/signals",
            "/backtests/{id}",
            "/risk/{id}",
            "/models",
            "/storage/presign",
        ):
            self.assertIn(path, paths)


def _registry(base_dir: Path):
    settings = load_runtime_settings(
        env={
            "DATA_LAKE_ROOT": str(base_dir / "lake"),
            "SQLITE_PATH": str(base_dir / "db.sqlite3"),
            "MODEL_CACHE_DIR": str(base_dir / "models"),
        },
        base_dir=base_dir,
    )
    return build_provider_registry(settings)


if __name__ == "__main__":
    unittest.main()
