"""Provider registry built from runtime settings."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.config.settings import RuntimeSettings
from src.providers.compute.base import ComputeProvider
from src.providers.compute.batch_stub import BatchStubComputeProvider
from src.providers.compute.dry_run import DryRunComputeProvider
from src.providers.compute.local import LocalComputeProvider
from src.providers.compute.runpod import RunPodComputeProvider
from src.providers.database.base import DatabaseProvider
from src.providers.database.postgres import PostgresDatabaseProvider
from src.providers.database.sqlite import SqliteDatabaseProvider
from src.providers.model_registry.base import ModelRegistryProvider
from src.providers.model_registry.hf_stub import HuggingFaceModelRegistryStub
from src.providers.model_registry.local import LocalModelRegistryProvider
from src.providers.model_registry.object_store import ObjectStoreModelRegistryProvider
from src.providers.provenance import build_provider_provenance
from src.providers.queue.base import QueueProvider
from src.providers.queue.local import LocalQueueProvider
from src.providers.queue.redis import RedisQueueProvider
from src.providers.rate_limit.base import RateLimitProvider
from src.providers.rate_limit.memory import MemoryRateLimitProvider
from src.providers.rate_limit.redis import RedisRateLimitProvider
from src.providers.secrets.base import SecretProvider
from src.providers.secrets.env import EnvSecretProvider
from src.providers.storage.base import StorageProvider
from src.providers.storage.local import LocalStorageProvider
from src.providers.storage.s3_compatible import S3CompatibleStorageProvider
from src.providers.warehouse.base import WarehouseProvider
from src.providers.warehouse.duckdb_provider import DuckDBWarehouseProvider


@dataclass(slots=True)
class ProviderRegistry:
    """Lazy provider registry for the configured runtime mode.

    Example:
        `registry = build_provider_registry(settings)`
    """

    settings: RuntimeSettings
    _storage: StorageProvider | None = field(default=None, init=False)
    _db: DatabaseProvider | None = field(default=None, init=False)
    _warehouse: WarehouseProvider | None = field(default=None, init=False)
    _queue: QueueProvider | None = field(default=None, init=False)
    _secrets: SecretProvider | None = field(default=None, init=False)
    _model_registry: ModelRegistryProvider | None = field(default=None, init=False)
    _compute: ComputeProvider | None = field(default=None, init=False)
    _rate_limit: RateLimitProvider | None = field(default=None, init=False)

    def get_storage(self) -> StorageProvider:
        """Return the configured storage provider."""
        if self._storage is None:
            self._storage = _build_storage(self.settings)
        return self._storage

    def get_db(self) -> DatabaseProvider:
        """Return the configured transactional database provider."""
        if self._db is None:
            self._db = _build_database(self.settings)
        return self._db

    def get_warehouse(self) -> WarehouseProvider:
        """Return the configured OLAP warehouse provider."""
        if self._warehouse is None:
            self._warehouse = DuckDBWarehouseProvider(self.settings.duckdb)
        return self._warehouse

    def get_queue(self) -> QueueProvider:
        """Return the configured queue provider."""
        if self._queue is None:
            self._queue = _build_queue(self.settings)
        return self._queue

    def get_secrets(self) -> SecretProvider:
        """Return the configured secret provider."""
        if self._secrets is None:
            self._secrets = EnvSecretProvider()
        return self._secrets

    def get_model_registry(self) -> ModelRegistryProvider:
        """Return the configured model registry provider."""
        if self._model_registry is None:
            self._model_registry = _build_model_registry(self.settings, self)
        return self._model_registry

    def get_compute(self) -> ComputeProvider:
        """Return the configured compute provider."""
        if self._compute is None:
            self._compute = _build_compute(self.settings)
        return self._compute

    def get_rate_limit(self) -> RateLimitProvider:
        """Return the configured rate-limit provider."""
        if self._rate_limit is None:
            self._rate_limit = _build_rate_limit(self.settings)
        return self._rate_limit


def build_provider_registry(settings: RuntimeSettings) -> ProviderRegistry:
    """Build a provider registry from runtime settings.

    Example:
        `registry = build_provider_registry(load_runtime_settings())`
    """
    return ProviderRegistry(settings)


__all__ = [
    "ProviderRegistry",
    "build_provider_registry",
    "build_provider_provenance",
]


def _build_storage(settings: RuntimeSettings) -> StorageProvider:
    if settings.storage.provider == "local":
        return LocalStorageProvider(settings.storage.local_root)
    return S3CompatibleStorageProvider(settings.storage)


def _build_database(settings: RuntimeSettings) -> DatabaseProvider:
    if settings.database.db_mode == "sqlite":
        return SqliteDatabaseProvider(settings.database)
    return PostgresDatabaseProvider(settings.database)


def _build_queue(settings: RuntimeSettings) -> QueueProvider:
    if settings.queue.provider == "local":
        return LocalQueueProvider()
    return RedisQueueProvider(settings.queue)


def _build_model_registry(
    settings: RuntimeSettings,
    registry: ProviderRegistry,
) -> ModelRegistryProvider:
    if settings.model.provider == "local":
        return LocalModelRegistryProvider(settings.model.cache_root)
    if settings.model.provider == "huggingface":
        return HuggingFaceModelRegistryStub()
    return ObjectStoreModelRegistryProvider(registry.get_storage())


def _build_compute(settings: RuntimeSettings) -> ComputeProvider:
    if settings.compute.provider == "local":
        return LocalComputeProvider()
    if settings.compute.provider == "runpod":
        return RunPodComputeProvider(settings)
    if settings.compute.provider == "stub":
        return DryRunComputeProvider()
    return BatchStubComputeProvider(settings.compute.provider)


def _build_rate_limit(settings: RuntimeSettings) -> RateLimitProvider:
    if settings.rate_limit.provider == "memory":
        return MemoryRateLimitProvider(settings.rate_limit)
    return RedisRateLimitProvider(settings.rate_limit)
