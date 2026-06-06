"""Manifest-aware storage facade for data lake and model artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.config.settings import RuntimeSettings, load_runtime_settings
from src.providers.registry import build_provider_registry
from src.providers.storage.base import StorageProvider
from src.storage.manifest import DatasetManifest, build_manifest, manifest_from_json
from src.storage.paths import DataLakePaths

PARQUET_CONTENT_TYPE = "application/vnd.apache.parquet"
JSON_CONTENT_TYPE = "application/json"
OCTET_STREAM_CONTENT_TYPE = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Stored object metadata returned by the facade."""

    path: str
    uri: str
    manifest_path: str


@dataclass(frozen=True, slots=True)
class StoredDatasetPartition:
    """Stored dataset partition metadata returned by the facade."""

    object: StoredObject
    manifest: DatasetManifest


@dataclass(frozen=True, slots=True)
class DataLakeArtifactStore:
    """Provider-neutral facade for data lake and artifact objects.

    Example:
        `store.save_dataset_partition("bars", "v1", {}, "part.parquet", b"...")`
    """

    storage: StorageProvider
    paths: DataLakePaths = DataLakePaths()

    def save_dataset_partition(
        self,
        dataset: str,
        version: str,
        partition: Mapping[str, str],
        filename: str,
        data: bytes,
        *,
        schema: Sequence[Mapping[str, object]],
        row_count: int,
        source: str,
        metadata: Mapping[str, object] | None = None,
    ) -> StoredDatasetPartition:
        """Store a Parquet dataset partition and write `_manifest.json`."""
        path = self.paths.parquet_dataset(dataset, version, partition, filename)
        return self._save_with_manifest(
            path,
            data,
            schema=schema,
            row_count=row_count,
            source=source,
            dataset=dataset,
            version=version,
            partition=partition,
            metadata=metadata,
            content_type=PARQUET_CONTENT_TYPE,
        )

    def save_raw_data(
        self,
        source_name: str,
        asset_type: str,
        symbol: str,
        timeframe: str,
        date: str,
        filename: str,
        data: bytes,
        *,
        schema: Sequence[Mapping[str, object]],
        row_count: int,
        source: str,
    ) -> StoredDatasetPartition:
        """Store a raw data lake object with a partition manifest."""
        path = self.paths.raw_data(
            source_name,
            asset_type,
            symbol,
            timeframe,
            date,
            filename,
        )
        partition = {
            "source": source_name,
            "asset_type": asset_type,
            "symbol": symbol,
            "timeframe": timeframe,
            "date": date,
        }
        return self._save_with_manifest(
            path,
            data,
            schema=schema,
            row_count=row_count,
            source=source,
            dataset="raw",
            version=date,
            partition=partition,
            metadata={},
            content_type=_content_type(filename),
        )

    def save_model_artifact(
        self,
        model_name: str,
        model_version: str,
        filename: str,
        data: bytes,
        *,
        source: str,
        metadata: Mapping[str, object] | None = None,
    ) -> StoredDatasetPartition:
        """Store a model artifact and version manifest."""
        path = self.paths.model_artifact(model_name, model_version, filename)
        return self._save_with_manifest(
            path,
            data,
            schema=[{"name": filename, "type": "binary"}],
            row_count=1,
            source=source,
            dataset=model_name,
            version=model_version,
            partition={},
            metadata=metadata,
            content_type=OCTET_STREAM_CONTENT_TYPE,
        )

    def save_backtest_report(
        self,
        run_id: str,
        filename: str,
        data: bytes,
        *,
        source: str,
        metadata: Mapping[str, object] | None = None,
    ) -> StoredDatasetPartition:
        """Store a backtest report and manifest."""
        path = self.paths.backtest_report(run_id, filename)
        return self._save_report(
            path,
            "backtest_report",
            run_id,
            data,
            source,
            metadata,
        )

    def save_risk_report(
        self,
        run_id: str,
        filename: str,
        data: bytes,
        *,
        source: str,
        metadata: Mapping[str, object] | None = None,
    ) -> StoredDatasetPartition:
        """Store a risk report and manifest."""
        path = self.paths.risk_report(run_id, filename)
        return self._save_report(path, "risk_report", run_id, data, source, metadata)

    def save_log(
        self,
        log_name: str,
        date: str,
        filename: str,
        data: bytes,
        *,
        source: str,
    ) -> StoredObject:
        """Store a log object without a dataset manifest."""
        path = self.paths.log_file(log_name, date, filename)
        uri = self.storage.put_bytes(path, data, "text/plain")
        return StoredObject(path, uri, "")

    def save_cached_dataset(
        self,
        dataset: str,
        version: str,
        filename: str,
        data: bytes,
        *,
        schema: Sequence[Mapping[str, object]],
        row_count: int,
        source: str,
    ) -> StoredDatasetPartition:
        """Store a cached dataset object and manifest."""
        path = self.paths.cached_dataset(dataset, version, filename)
        return self._save_with_manifest(
            path,
            data,
            schema=schema,
            row_count=row_count,
            source=source,
            dataset=dataset,
            version=version,
            partition={},
            metadata={"cache": True},
            content_type=_content_type(filename),
        )

    def read_manifest(self, manifest_path: str) -> dict[str, object]:
        """Read a stored `_manifest.json` payload."""
        return manifest_from_json(self.storage.get_bytes(manifest_path))

    def _save_report(
        self,
        path: str,
        dataset: str,
        run_id: str,
        data: bytes,
        source: str,
        metadata: Mapping[str, object] | None,
    ) -> StoredDatasetPartition:
        return self._save_with_manifest(
            path,
            data,
            schema=[{"name": "report", "type": "document"}],
            row_count=1,
            source=source,
            dataset=dataset,
            version=run_id,
            partition={"run_id": run_id},
            metadata=metadata,
            content_type=_content_type(path),
        )

    def _save_with_manifest(
        self,
        path: str,
        data: bytes,
        *,
        schema: Sequence[Mapping[str, object]],
        row_count: int,
        source: str,
        dataset: str,
        version: str,
        partition: Mapping[str, str],
        metadata: Mapping[str, object] | None,
        content_type: str,
    ) -> StoredDatasetPartition:
        uri = self.storage.put_bytes(path, data, content_type)
        manifest_path = self.paths.manifest_for(path)
        manifest = build_manifest(
            data,
            schema,
            row_count,
            source,
            dataset=dataset,
            version=version,
            partition=partition,
            object_path=path,
            object_uri=uri,
            metadata=metadata,
        )
        self.storage.put_bytes(
            manifest_path,
            manifest.to_json_bytes(),
            JSON_CONTENT_TYPE,
        )
        return StoredDatasetPartition(StoredObject(path, uri, manifest_path), manifest)


def _content_type(path: str) -> str:
    if path.endswith(".json"):
        return JSON_CONTENT_TYPE
    if path.endswith(".parquet"):
        return PARQUET_CONTENT_TYPE
    if path.endswith(".txt") or path.endswith(".log"):
        return "text/plain"
    return OCTET_STREAM_CONTENT_TYPE


def build_data_lake_store(
    settings: RuntimeSettings | None = None,
    paths: DataLakePaths | None = None,
) -> DataLakeArtifactStore:
    """Build the data lake facade from runtime environment settings."""
    active_settings = settings or load_runtime_settings()
    registry = build_provider_registry(active_settings)
    return DataLakeArtifactStore(registry.get_storage(), paths or DataLakePaths())
