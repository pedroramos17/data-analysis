"""Runtime mode settings for local and cheap-cloud Quant deployments."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import ParseResult, parse_qs, unquote, urlparse

AppEnv = Literal["local", "cloud", "test"]
ComputeProvider = Literal["local", "colab", "vastai", "gcp", "aws"]
DbMode = Literal["sqlite", "postgres"]
DeploymentMode = Literal["onprem", "cloud_mvp", "cloud_prod"]
ModelProvider = Literal["local", "huggingface", "s3", "r2"]
OlapMode = Literal["duckdb"]
QueueProvider = Literal["local", "redis", "sqs", "rabbitmq"]
SecretsProvider = Literal["env", "aws_secrets", "gcp_secret_manager", "doppler"]
StorageProvider = Literal["local", "s3", "r2", "b2", "minio"]

APP_ENVS = ("local", "cloud", "test")
COMPUTE_PROVIDERS = ("local", "colab", "vastai", "gcp", "aws")
DB_MODES = ("sqlite", "postgres")
DEPLOYMENT_MODES = ("onprem", "cloud_mvp", "cloud_prod")
MODEL_PROVIDERS = ("local", "huggingface", "s3", "r2")
OLAP_MODES = ("duckdb",)
QUEUE_PROVIDERS = ("local", "redis", "sqs", "rabbitmq")
SECRETS_PROVIDERS = ("env", "aws_secrets", "gcp_secret_manager", "doppler")
STORAGE_PROVIDERS = ("local", "s3", "r2", "b2", "minio")

DEFAULT_SQLITE_TIMEOUT_SECONDS = 30
DEFAULT_DATA_LAKE_PATH = Path("data") / "lake"
DEFAULT_DUCKDB_FILENAME = "analytics.duckdb"
DEFAULT_MODEL_CACHE_PATH = Path("models")
DEFAULT_MONTHLY_BUDGET_USD = 25.0
DEFAULT_MAX_JOB_COST_USD = 2.5


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Transactional metadata database settings.

    Example:
        `load_runtime_settings(env={}).database.as_django_database()`
    """

    db_mode: DbMode
    sqlite_path: Path
    postgres_url: str = ""
    sqlite_timeout_seconds: int = DEFAULT_SQLITE_TIMEOUT_SECONDS

    def as_django_database(self) -> dict[str, object]:
        """Return the Django `DATABASES["default"]` dictionary."""
        if self.db_mode == "sqlite":
            return {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": self.sqlite_path,
                "OPTIONS": {"timeout": self.sqlite_timeout_seconds},
            }
        return _postgres_django_database(self.postgres_url)


@dataclass(frozen=True, slots=True)
class StorageSettings:
    """Object storage settings with local filesystem fallback.

    Example:
        `settings.storage.provider == "local"`
    """

    provider: StorageProvider
    local_root: Path
    bucket_name: str = ""
    endpoint_url: str = ""
    access_key_id: str = ""
    secret_access_key: str = ""
    region_name: str = ""

    def uses_remote_object_storage(self) -> bool:
        """Return whether this provider needs S3-compatible object storage."""
        return self.provider != "local"


@dataclass(frozen=True, slots=True)
class DuckDBSettings:
    """Embedded OLAP settings over local or mounted Parquet data.

    Example:
        `settings.duckdb.database_path`
    """

    olap_mode: OlapMode
    database_path: Path
    data_lake_root: Path


@dataclass(frozen=True, slots=True)
class QueueSettings:
    """Queue provider settings with no-queue local fallback.

    Example:
        `settings.queue.provider == "local"`
    """

    provider: QueueProvider
    connection_url: str = ""


@dataclass(frozen=True, slots=True)
class ModelSettings:
    """Pre-trained model artifact and cache settings.

    Example:
        `settings.model.cache_root`
    """

    provider: ModelProvider
    cache_root: Path
    registry_uri: str = ""


@dataclass(frozen=True, slots=True)
class ComputeSettings:
    """Compute provider settings for CPU-first inference and batch hooks.

    Example:
        `settings.compute.gpu_required`
    """

    provider: ComputeProvider
    gpu_required: bool = False
    gpu_batch_enabled: bool = False


@dataclass(frozen=True, slots=True)
class CloudCostSettings:
    """Budget guard settings for cheap-cloud execution.

    Example:
        `settings.cost.monthly_budget_usd`
    """

    monthly_budget_usd: float
    max_job_cost_usd: float
    require_budget_approval: bool = True


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Unified runtime settings for local, test, and cloud modes.

    Example:
        `settings = load_runtime_settings(env={"APP_ENV": "test"})`
    """

    app_env: AppEnv
    deployment_mode: DeploymentMode
    database: DatabaseSettings
    storage: StorageSettings
    duckdb: DuckDBSettings
    queue: QueueSettings
    secrets_provider: SecretsProvider
    model: ModelSettings
    compute: ComputeSettings
    cost: CloudCostSettings


def load_runtime_settings(
    env: Mapping[str, str] | None = None,
    base_dir: Path | None = None,
) -> RuntimeSettings:
    """Load runtime settings from injected env values or `os.environ`.

    Example:
        `settings = load_runtime_settings(env={}, base_dir=Path.cwd())`
    """
    source_env = os.environ if env is None else env
    root = Path.cwd() if base_dir is None else base_dir
    app_env = _choice(source_env, "APP_ENV", "local", APP_ENVS)
    deployment = _deployment_mode(source_env, app_env)
    return RuntimeSettings(
        app_env=app_env,
        deployment_mode=deployment,
        database=_database_settings(source_env, root, deployment),
        storage=_storage_settings(source_env, root, deployment),
        duckdb=_duckdb_settings(source_env, root),
        queue=_queue_settings(source_env),
        secrets_provider=_choice(
            source_env,
            "SECRETS_PROVIDER",
            "env",
            SECRETS_PROVIDERS,
        ),
        model=_model_settings(source_env, root),
        compute=_compute_settings(source_env),
        cost=_cost_settings(source_env),
    )


def _database_settings(
    env: Mapping[str, str],
    base_dir: Path,
    deployment_mode: DeploymentMode,
) -> DatabaseSettings:
    default_mode = "postgres" if deployment_mode != "onprem" else "sqlite"
    db_mode = _choice(env, "DB_MODE", default_mode, DB_MODES)
    sqlite_path = _path_value(env, "SQLITE_PATH", base_dir / "db.sqlite3")
    if db_mode == "sqlite":
        return DatabaseSettings(db_mode, sqlite_path)
    postgres_url = _required_value(
        env,
        "DATABASE_URL",
        "postgresql://user:password@host:5432/database",
    )
    return DatabaseSettings(db_mode, sqlite_path, postgres_url)


def _storage_settings(
    env: Mapping[str, str],
    base_dir: Path,
    deployment_mode: DeploymentMode,
) -> StorageSettings:
    default_provider = "s3" if deployment_mode != "onprem" else "local"
    provider = _choice(env, "STORAGE_PROVIDER", default_provider, STORAGE_PROVIDERS)
    local_root = _path_value(env, "DATA_LAKE_ROOT", base_dir / DEFAULT_DATA_LAKE_PATH)
    if provider == "local":
        return StorageSettings(provider, local_root)
    return _remote_storage_settings(env, provider, local_root)


def _remote_storage_settings(
    env: Mapping[str, str],
    provider: StorageProvider,
    local_root: Path,
) -> StorageSettings:
    return StorageSettings(
        provider=provider,
        local_root=local_root,
        bucket_name=_required_value(env, "OBJECT_STORAGE_BUCKET", "bucket name"),
        endpoint_url=_env_value(env, "OBJECT_STORAGE_ENDPOINT_URL", ""),
        access_key_id=_storage_access_key(env),
        secret_access_key=_storage_secret_key(env),
        region_name=_env_value(env, "OBJECT_STORAGE_REGION", "auto"),
    )


def _duckdb_settings(env: Mapping[str, str], base_dir: Path) -> DuckDBSettings:
    olap_mode = _choice(env, "OLAP_MODE", "duckdb", OLAP_MODES)
    lake_root = _path_value(env, "DATA_LAKE_ROOT", base_dir / DEFAULT_DATA_LAKE_PATH)
    duckdb_path = _path_value(
        env,
        "DUCKDB_PATH",
        lake_root / DEFAULT_DUCKDB_FILENAME,
    )
    return DuckDBSettings(olap_mode, duckdb_path, lake_root)


def _queue_settings(env: Mapping[str, str]) -> QueueSettings:
    provider = _choice(env, "QUEUE_PROVIDER", "local", QUEUE_PROVIDERS)
    if provider == "local":
        return QueueSettings(provider)
    return QueueSettings(provider, _queue_connection_url(env, provider))


def _model_settings(env: Mapping[str, str], base_dir: Path) -> ModelSettings:
    provider = _choice(env, "MODEL_PROVIDER", "local", MODEL_PROVIDERS)
    cache_root = _path_value(
        env,
        "MODEL_CACHE_DIR",
        base_dir / DEFAULT_MODEL_CACHE_PATH,
    )
    registry_uri = _env_value(env, "MODEL_REGISTRY_URI", str(cache_root))
    return ModelSettings(provider, cache_root, registry_uri)


def _compute_settings(env: Mapping[str, str]) -> ComputeSettings:
    provider = _choice(env, "COMPUTE_PROVIDER", "local", COMPUTE_PROVIDERS)
    gpu_required = _bool_value(env, "GPU_REQUIRED", False)
    gpu_batch_enabled = _bool_value(env, "GPU_BATCH_ENABLED", False)
    return ComputeSettings(provider, gpu_required, gpu_batch_enabled)


def _cost_settings(env: Mapping[str, str]) -> CloudCostSettings:
    return CloudCostSettings(
        monthly_budget_usd=_float_value(
            env,
            "CLOUD_MONTHLY_BUDGET_USD",
            DEFAULT_MONTHLY_BUDGET_USD,
        ),
        max_job_cost_usd=_float_value(
            env,
            "CLOUD_MAX_JOB_COST_USD",
            DEFAULT_MAX_JOB_COST_USD,
        ),
        require_budget_approval=_bool_value(env, "CLOUD_REQUIRE_BUDGET_APPROVAL", True),
    )


def _deployment_mode(
    env: Mapping[str, str],
    app_env: AppEnv,
) -> DeploymentMode:
    default_mode = "cloud_mvp" if app_env == "cloud" else "onprem"
    return _choice(env, "DEPLOYMENT_MODE", default_mode, DEPLOYMENT_MODES)


def _postgres_django_database(database_url: str) -> dict[str, object]:
    parsed_url = urlparse(database_url)
    _validate_postgres_url(database_url, parsed_url)
    config = _base_postgres_config(parsed_url)
    options = _postgres_options(parsed_url.query)
    if options:
        config["OPTIONS"] = options
    return config


def _base_postgres_config(parsed_url: ParseResult) -> dict[str, object]:
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(str(parsed_url.path).lstrip("/")),
        "USER": unquote(parsed_url.username or ""),
        "PASSWORD": unquote(parsed_url.password or ""),
        "HOST": parsed_url.hostname or "",
        "PORT": str(parsed_url.port or ""),
    }


def _postgres_options(query_string: str) -> dict[str, object]:
    query = parse_qs(query_string)
    sslmode = query.get("sslmode", [""])[0]
    if not sslmode:
        return {}
    return {"sslmode": sslmode}


def _validate_postgres_url(database_url: str, parsed_url: ParseResult) -> None:
    valid_scheme = parsed_url.scheme in {"postgres", "postgresql"}
    has_shape = bool(parsed_url.hostname and str(parsed_url.path).strip("/"))
    if valid_scheme and has_shape:
        return
    raise ValueError(
        f"Invalid DATABASE_URL {database_url!r}; expected "
        "postgresql://user:password@host:5432/database"
    )


def _choice(
    env: Mapping[str, str],
    key: str,
    default_value: str,
    allowed_values: tuple[str, ...],
) -> str:
    value = _env_value(env, key, default_value)
    if value in allowed_values:
        return value
    raise ValueError(
        f"Invalid {key} {value!r}; expected one of {allowed_values!r}"
    )


def _path_value(env: Mapping[str, str], key: str, default_path: Path) -> Path:
    value = _env_value(env, key, "")
    if value:
        return Path(value)
    return default_path


def _bool_value(env: Mapping[str, str], key: str, default_value: bool) -> bool:
    value = _env_value(env, key, "")
    if not value:
        return default_value
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid {key} {value!r}; expected true or false")


def _float_value(env: Mapping[str, str], key: str, default_value: float) -> float:
    value = _env_value(env, key, "")
    if not value:
        return default_value
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {key} {value!r}; expected numeric value") from exc


def _required_value(env: Mapping[str, str], key: str, expected_shape: str) -> str:
    value = _env_value(env, key, "")
    if value:
        return value
    raise ValueError(f"Invalid {key} {value!r}; expected {expected_shape}")


def _env_value(env: Mapping[str, str], key: str, default_value: str) -> str:
    value = env.get(key)
    if value is None:
        return default_value
    return value.strip()


def _storage_access_key(env: Mapping[str, str]) -> str:
    value = _env_value(env, "OBJECT_STORAGE_ACCESS_KEY_ID", "")
    if value:
        return value
    return _required_value(env, "AWS_ACCESS_KEY_ID", "object storage access key")


def _storage_secret_key(env: Mapping[str, str]) -> str:
    value = _env_value(env, "OBJECT_STORAGE_SECRET_ACCESS_KEY", "")
    if value:
        return value
    return _required_value(env, "AWS_SECRET_ACCESS_KEY", "object storage secret key")


def _queue_connection_url(env: Mapping[str, str], provider: QueueProvider) -> str:
    provider_key = _queue_provider_url_key(provider)
    value = _env_value(env, provider_key, "")
    if value:
        return value
    return _required_value(env, "QUEUE_URL", f"{provider} connection URL")


def _queue_provider_url_key(provider: QueueProvider) -> str:
    if provider == "redis":
        return "REDIS_URL"
    if provider == "sqs":
        return "SQS_QUEUE_URL"
    return "RABBITMQ_URL"
