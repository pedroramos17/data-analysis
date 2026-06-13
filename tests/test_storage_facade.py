"""Tests for provider-neutral object storage facade."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from src.providers.storage.local import LocalStorageProvider
from src.storage import DataLakeArtifactStore, DataLakePaths


class StorageFacadeTests(unittest.TestCase):
    """The same facade must work for local and object-store providers."""

    def test_local_dataset_partition_writes_manifest_next_to_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataLakeArtifactStore(LocalStorageProvider(Path(temp_dir)))

            result = store.save_dataset_partition(
                "market_bars",
                "2026-06-02",
                {"symbol": "SPY", "timeframe": "1d"},
                "part-000.parquet",
                b"parquet-bytes",
                schema=[{"name": "close", "type": "double"}],
                row_count=10,
                source="unit-test",
            )

            self.assertTrue((Path(temp_dir) / result.object.path).exists())
            manifest = store.read_manifest(result.object.manifest_path)
            self.assertEqual(manifest["row_count"], 10)
            self.assertEqual(manifest["source"], "unit-test")
            self.assertEqual(manifest["schema"], [{"name": "close", "type": "double"}])
            self.assertEqual(manifest["content_hash"], result.manifest.content_hash)
            self.assertTrue(manifest["content_hash"].startswith("sha256:"))

    def test_fake_remote_provider_uses_same_dataset_code_path(self) -> None:
        fake = InMemoryStorageProvider("r2://quant-lake")
        store = DataLakeArtifactStore(fake)

        result = store.save_dataset_partition(
            "features",
            "v1",
            {"symbol": "AAPL"},
            "part-000.parquet",
            b"feature-bytes",
            schema=[{"name": "feature_value", "type": "double"}],
            row_count=3,
            source="feature-builder",
        )

        self.assertEqual(result.object.uri, "r2://quant-lake/" + result.object.path)
        self.assertIn(result.object.path, fake.objects)
        self.assertIn(result.object.manifest_path, fake.objects)
        manifest = store.read_manifest(result.object.manifest_path)
        self.assertEqual(manifest["object_uri"], result.object.uri)
        self.assertEqual(manifest["partition"], {"symbol": "AAPL"})

    def test_facade_can_be_built_from_local_runtime_settings(self) -> None:
        from src.config.settings import load_runtime_settings
        from src.storage import build_data_lake_store

        with tempfile.TemporaryDirectory() as temp_dir:
            settings = load_runtime_settings(env={}, base_dir=Path(temp_dir))

            store = build_data_lake_store(settings)
            result = store.save_cached_dataset(
                "panel",
                "v1",
                "panel.parquet",
                b"panel-bytes",
                schema=[{"name": "symbol", "type": "string"}],
                row_count=1,
                source="unit-test",
            )

            self.assertTrue(result.object.uri.startswith("file:"))
            self.assertTrue(
                settings.storage.local_root.joinpath(result.object.path).exists()
            )

    def test_storage_paths_cover_required_artifact_categories(self) -> None:
        paths = DataLakePaths()

        self.assertEqual(
            paths.raw_data("yahoo", "equity", "SPY", "1d", "2026-06-02", "x.parquet"),
            "raw/source=yahoo/asset_type=equity/symbol=SPY/timeframe=1d/"
            "date=2026-06-02/x.parquet",
        )
        self.assertEqual(
            paths.model_artifact("mamba", "v1", "weights.bin"),
            "models/model_name=mamba/model_version=v1/weights.bin",
        )
        self.assertEqual(
            paths.backtest_report("run-1", "report.json"),
            "backtests/reports/run_id=run-1/report.json",
        )
        self.assertEqual(
            paths.risk_report("risk-1", "report.json"),
            "risk/reports/run_id=risk-1/report.json",
        )
        self.assertEqual(
            paths.log_file("worker", "2026-06-02", "worker.log"),
            "logs/log=worker/date=2026-06-02/worker.log",
        )
        self.assertEqual(
            paths.cached_dataset("panel", "v1", "panel.parquet"),
            "cache/datasets/dataset=panel/version=v1/panel.parquet",
        )

    def test_business_logic_does_not_import_boto3_directly(self) -> None:
        src_root = Path(__file__).resolve().parents[1] / "src"
        allowed = src_root / "providers" / "storage" / "s3_compatible.py"
        offenders: list[str] = []
        for path in src_root.rglob("*.py"):
            if path == allowed:
                continue
            text = path.read_text(encoding="utf-8")
            if "import boto3" in text or "from boto3" in text:
                offenders.append(path.relative_to(src_root).as_posix())

        self.assertEqual(offenders, [])


@dataclass(slots=True)
class InMemoryStorageProvider:
    """Fake object-store provider for facade tests."""

    uri_prefix: str
    objects: dict[str, bytes] = field(default_factory=dict)

    def put_bytes(
        self,
        path: str,
        data: bytes,
        content_type: str | None = None,
    ) -> str:
        self.objects[path] = data
        return f"{self.uri_prefix}/{path}"

    def get_bytes(self, path: str) -> bytes:
        return self.objects[path]

    def exists(self, path: str) -> bool:
        return path in self.objects

    def list(self, prefix: str) -> list[str]:
        return sorted(path for path in self.objects if path.startswith(prefix))

    def delete(self, path: str) -> None:
        self.objects.pop(path, None)

    def presign_read(self, path: str, expires_seconds: int) -> str:
        return f"{self.uri_prefix}/{path}?expires={expires_seconds}"
