"""Runtime mode settings for local and cheap-cloud Quant deployments."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import ParseResult, parse_qs, quote, urlencode, unquote, urlparse

AppEnv = Literal["local", "test", "cloud"]
ComputeProvider = Literal["local", "runpod", "colab", "vastai", "stub"]
CostMode = Literal["minimum", "balanced", "performance"]
DbMode = Literal["sqlite", "postgres"]
DeploymentMode = Literal["onprem", "cloud_mvp", "cloud_gpu"]
ModelProvider = Literal["local", "huggingface", "s3", "r2"]
ModelDevice = Literal["cpu", "cuda", "auto"]
OlapMode = Literal["duckdb"]
OrchestratorProvider = Literal["local", "apscheduler", "prefect", "dagster"]
QueueProvider = Literal["local", "redis"]
RateLimitProvider = Literal["memory", "redis"]
SecretsProvider = Literal["env", "aws_secrets", "gcp_secret_manager", "doppler"]
StorageProvider = Literal["local", "s3", "r2", "b2", "minio"]

APP_ENVS = ("local", "cloud", "test")
COMPUTE_PROVIDERS = ("local", "runpod", "colab", "vastai", "stub")
COST_MODES = ("minimum", "balanced", "performance")
DB_MODES = ("sqlite", "postgres")
DEPLOYMENT_MODES = ("onprem", "cloud_mvp", "cloud_gpu")
MODEL_PROVIDERS = ("local", "huggingface", "s3", "r2")
MODEL_DEVICES = ("cpu", "cuda", "auto")
OLAP_MODES = ("duckdb",)
ORCHESTRATORS = ("local", "apscheduler", "prefect", "dagster")
QUEUE_PROVIDERS = ("local", "redis")
RATE_LIMIT_PROVIDERS = ("memory", "redis")
SECRETS_PROVIDERS = ("env", "aws_secrets", "gcp_secret_manager", "doppler")
STORAGE_PROVIDERS = ("local", "s3", "r2", "b2", "minio")

DEFAULT_SQLITE_TIMEOUT_SECONDS = 30
DEFAULT_DATA_LAKE_PATH = Path("data") / "lake"
DEFAULT_DUCKDB_FILENAME = "analytics.duckdb"
DEFAULT_MODEL_CACHE_PATH = Path("models")
DEFAULT_MONTHLY_BUDGET_USD = 25.0
DEFAULT_MAX_JOB_COST_USD = 2.5
DEFAULT_POSTGRES_PORT = "5432"
DEFAULT_RUNPOD_MAX_RUNTIME_SECONDS = 3600
DEFAULT_RUNPOD_IMAGE = "ghcr.io/pedroramos17/data-analysis:latest"
AUTOSCALING_DEFAULT_MAX_WORKERS = 1


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
class PipelineSettings:
    """High-level pipeline runtime controls.

    Example:
        `settings.pipeline.orchestrator == "local"`
    """

    orchestrator: OrchestratorProvider
    model_device: ModelDevice
    cost_mode: CostMode
    cloud_tests_enabled: bool = False
    external_paid_api_calls_enabled: bool = False


@dataclass(frozen=True, slots=True)
class SlidingWindowSettings:
    """Default leakage-aware sliding-window settings."""

    strategy: str = "purged_walk_forward"
    train_size: int = 252
    validation_size: int = 21
    test_size: int = 21
    step_size: int = 21
    embargo: int = 1
    horizon: int = 1


@dataclass(frozen=True, slots=True)
class RunPodSettings:
    """RunPod provider settings for optional hourly GPU jobs."""

    api_key: str = ""
    endpoint_url: str = "https://api.runpod.io/graphql"
    template_id: str = ""
    endpoint_id: str = ""
    gpu_type: str = "NVIDIA RTX A4000"
    image: str = DEFAULT_RUNPOD_IMAGE
    allowed_images: tuple[str, ...] = (DEFAULT_RUNPOD_IMAGE,)
    network_volume_id: str = ""
    container_disk_gb: int = 40
    volume_gb: int = 0
    max_runtime_seconds: int = DEFAULT_RUNPOD_MAX_RUNTIME_SECONDS
    max_job_minutes: int = 60
    idle_timeout_seconds: int = 300
    min_gpu_memory_gb: int = 16
    max_hourly_cost_usd: float = 0.75
    max_dataset_size_gb: float = 100.0
    enable_spot: bool = False
    enable_public_jupyter: bool = False
    enable_ssh: bool = False
    terminate_on_completion: bool = True
    dry_run: bool = True


@dataclass(frozen=True, slots=True)
class AutoscalingSettings:
    """Autoscaling policy settings for future workers/pods."""

    enabled: bool = False
    min_workers: int = 0
    max_workers: int = 1
    max_concurrent_gpu_jobs: int = 1
    max_gpu_workers: int = 1
    max_cpu_workers: int = 2
    queue_check_interval_seconds: int = 30
    scale_to_zero: bool = True
    idle_timeout_seconds: int = 300
    max_hourly_budget_usd: float = 1.0
    max_daily_budget_usd: float = 5.0
    prefer_spot: bool = True
    batch_small_jobs: bool = True


@dataclass(frozen=True, slots=True)
class RateLimitSettings:
    """Rate-limit provider settings for ingestion and API jobs."""

    provider: RateLimitProvider
    requests_per_minute: int = 60
    burst: int = 10
    redis_url: str = ""
    anonymous_requests_per_minute: int = 20
    authenticated_requests_per_minute: int = 120
    gpu_submit_requests_per_hour: int = 3
    gpu_submit_requests_per_day: int = 10
    ingestion_requests_per_hour: int = 10
    training_requests_per_hour: int = 5
    features_requests_per_hour: int = 20
    predict_requests_per_minute: int = 60
    health_requests_per_minute: int = 600


@dataclass(frozen=True, slots=True)
class EfficiencySettings:
    """Code-efficiency measurement settings for pipeline stages."""

    enabled: bool = True
    sample_rate: float = 1.0
    record_memory: bool = True
    record_timing: bool = True
    output_path: Path = Path("data") / "lake" / "metrics" / "efficiency.jsonl"
    report_root: Path = Path("reports") / "efficiency"
    max_pipeline_minutes_local: float = 30.0
    max_peak_memory_mb: float = 4096.0
    min_rows_per_second: float = 10000.0
    max_gpu_job_minutes: float = 60.0
    max_cost_per_run_usd: float = 2.0


@dataclass(frozen=True, slots=True)
class CostGuardSettings:
    """Budget guard settings for local, cloud MVP, and cloud GPU execution.

    Example:
        `settings.cost.monthly_budget_usd`
    """

    cost_mode: CostMode
    monthly_budget_usd: float
    max_job_cost_usd: float
    max_gpu_hourly_cost_usd: float = 0.75
    require_budget_approval: bool = True
    external_paid_api_calls_enabled: bool = False
    cloud_tests_enabled: bool = False


CloudCostSettings = CostGuardSettings


@dataclass(frozen=True, slots=True)
class SecuritySettings:
    """Security defaults for local and cloud pipeline execution."""

    require_secrets_for_launch: bool = True
    allow_shell_commands: bool = False
    redact_secrets: bool = True
    require_signed_job_manifest: bool = False
    terminate_remote_on_timeout: bool = True
    api_auth_enabled: bool = True
    read_only_requires_auth: bool = False
    api_key_hashes: tuple[str, ...] = ()
    cors_allowed_origins: tuple[str, ...] = ("http://localhost:8000", "http://127.0.0.1:8000")
    max_presigned_url_expiry_seconds: int = 300
    allowed_storage_prefixes: tuple[str, ...] = ("data/", "datasets/", "reports/", "models/", "exports/", "logs/", "metrics/")
    allowed_config_roots: tuple[str, ...] = ("configs",)
    audit_log_path: Path = Path("data") / "lake" / "audit" / "security_audit.jsonl"


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
    pipeline: PipelineSettings
    sliding_window: SlidingWindowSettings
    runpod: RunPodSettings
    autoscaling: AutoscalingSettings
    rate_limit: RateLimitSettings
    efficiency: EfficiencySettings
    cost: CostGuardSettings
    security: SecuritySettings


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
        compute=_compute_settings(source_env, deployment),
        pipeline=_pipeline_settings(source_env),
        sliding_window=_sliding_window_settings(source_env),
        runpod=_runpod_settings(source_env),
        autoscaling=_autoscaling_settings(source_env),
        rate_limit=_rate_limit_settings(source_env),
        efficiency=_efficiency_settings(source_env, root),
        cost=_cost_settings(source_env),
        security=_security_settings(source_env),
    )


def _database_settings(
    env: Mapping[str, str],
    base_dir: Path,
    deployment_mode: DeploymentMode,
) -> DatabaseSettings:
    default_mode = "postgres" if _postgres_configured(env, deployment_mode) else "sqlite"
    db_mode = _choice(env, "DB_MODE", default_mode, DB_MODES)
    sqlite_path = _path_value(env, "SQLITE_PATH", base_dir / "db.sqlite3")
    if db_mode == "sqlite":
        return DatabaseSettings(db_mode, sqlite_path)
    postgres_url = _postgres_url(env)
    return DatabaseSettings(db_mode, sqlite_path, postgres_url)


def _storage_settings(
    env: Mapping[str, str],
    base_dir: Path,
    deployment_mode: DeploymentMode,
) -> StorageSettings:
    default_provider = "s3" if _object_storage_configured(env, deployment_mode) else "local"
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
    default_provider = "s3" if _env_value(env, "MODEL_REGISTRY_URI", "").startswith("s3://") else "local"
    provider = _choice(env, "MODEL_PROVIDER", default_provider, MODEL_PROVIDERS)
    cache_root = _path_value(
        env,
        "MODEL_CACHE_DIR",
        base_dir / DEFAULT_MODEL_CACHE_PATH,
    )
    registry_uri = _env_value(env, "MODEL_REGISTRY_URI", str(cache_root))
    return ModelSettings(provider, cache_root, registry_uri)


def _compute_settings(
    env: Mapping[str, str],
    deployment_mode: DeploymentMode,
) -> ComputeSettings:
    default_provider = "runpod" if deployment_mode == "cloud_gpu" else "local"
    provider = _choice(env, "COMPUTE_PROVIDER", default_provider, COMPUTE_PROVIDERS)
    gpu_required = _bool_value(env, "GPU_REQUIRED", False)
    gpu_batch_enabled = _bool_value(env, "GPU_BATCH_ENABLED", False)
    return ComputeSettings(provider, gpu_required, gpu_batch_enabled)


def _pipeline_settings(env: Mapping[str, str]) -> PipelineSettings:
    cost_mode = _choice(env, "COST_MODE", "minimum", COST_MODES)
    return PipelineSettings(
        orchestrator=_choice(env, "ORCHESTRATOR", "local", ORCHESTRATORS),
        model_device=_choice(env, "MODEL_DEVICE", "cpu", MODEL_DEVICES),
        cost_mode=cost_mode,
        cloud_tests_enabled=_bool_value(env, "ENABLE_CLOUD_TESTS", False),
        external_paid_api_calls_enabled=_bool_value(
            env,
            "ALLOW_EXTERNAL_PAID_API_CALLS",
            False,
        ),
    )


def _sliding_window_settings(env: Mapping[str, str]) -> SlidingWindowSettings:
    return SlidingWindowSettings(
        strategy=_env_value(env, "SLIDING_WINDOW_STRATEGY", "purged_walk_forward"),
        train_size=_int_value(env, "SLIDING_WINDOW_TRAIN_SIZE", 252),
        validation_size=_int_value(env, "SLIDING_WINDOW_VALIDATION_SIZE", 21),
        test_size=_int_value(env, "SLIDING_WINDOW_TEST_SIZE", 21),
        step_size=_int_value(env, "SLIDING_WINDOW_STEP_SIZE", 21),
        embargo=_int_value(env, "SLIDING_WINDOW_EMBARGO", 1),
        horizon=_int_value(env, "SLIDING_WINDOW_HORIZON", 1),
    )


def _runpod_settings(env: Mapping[str, str]) -> RunPodSettings:
    image = _env_value(env, "RUNPOD_IMAGE", DEFAULT_RUNPOD_IMAGE)
    allowed_images = _csv_value(env, "RUNPOD_ALLOWED_IMAGES") or (image,)
    return RunPodSettings(
        api_key=_env_value(env, "RUNPOD_API_KEY", ""),
        endpoint_url=_env_value(env, "RUNPOD_ENDPOINT_URL", "https://api.runpod.io/graphql"),
        template_id=_env_value(env, "RUNPOD_TEMPLATE_ID", ""),
        endpoint_id=_env_value(env, "RUNPOD_ENDPOINT_ID", ""),
        gpu_type=_env_value(env, "RUNPOD_GPU_TYPE", "NVIDIA RTX A4000"),
        image=image,
        allowed_images=allowed_images,
        network_volume_id=_env_value(env, "RUNPOD_NETWORK_VOLUME_ID", ""),
        container_disk_gb=_int_value(env, "RUNPOD_CONTAINER_DISK_GB", 40),
        volume_gb=_int_value(env, "RUNPOD_VOLUME_GB", 0),
        max_runtime_seconds=_int_value(
            env,
            "RUNPOD_MAX_RUNTIME_SECONDS",
            DEFAULT_RUNPOD_MAX_RUNTIME_SECONDS,
        ),
        max_job_minutes=_int_value(env, "RUNPOD_MAX_JOB_MINUTES", 60),
        idle_timeout_seconds=_int_value(env, "RUNPOD_IDLE_TIMEOUT_SECONDS", 300),
        min_gpu_memory_gb=_int_value(env, "RUNPOD_MIN_GPU_MEMORY_GB", 16),
        max_hourly_cost_usd=_float_value(
            env,
            "RUNPOD_MAX_HOURLY_COST",
            _float_value(env, "MAX_GPU_HOURLY_COST_USD", 0.75),
        ),
        max_dataset_size_gb=_float_value(env, "RUNPOD_MAX_DATASET_SIZE_GB", 100.0),
        enable_spot=_bool_value(env, "RUNPOD_ENABLE_SPOT", False),
        enable_public_jupyter=_bool_value(env, "RUNPOD_ENABLE_PUBLIC_JUPYTER", False),
        enable_ssh=_bool_value(env, "RUNPOD_ENABLE_SSH", False),
        terminate_on_completion=_bool_value(env, "RUNPOD_TERMINATE_ON_COMPLETION", True),
        dry_run=_bool_value(env, "RUNPOD_DRY_RUN", True),
    )


def _autoscaling_settings(env: Mapping[str, str]) -> AutoscalingSettings:
    max_gpu_workers = _int_value(
        env,
        "AUTOSCALING_MAX_GPU_WORKERS",
        _int_value(env, "MAX_CONCURRENT_GPU_JOBS", 1),
    )
    max_workers = _int_value(env, "AUTOSCALING_MAX_WORKERS", max_gpu_workers)
    return AutoscalingSettings(
        enabled=_bool_value(env, "AUTOSCALING_ENABLED", False),
        min_workers=_int_value(env, "AUTOSCALING_MIN_WORKERS", 0),
        max_workers=max(max_workers, max_gpu_workers),
        max_concurrent_gpu_jobs=max_gpu_workers,
        max_gpu_workers=max_gpu_workers,
        max_cpu_workers=_int_value(env, "AUTOSCALING_MAX_CPU_WORKERS", 2),
        queue_check_interval_seconds=_int_value(env, "AUTOSCALING_QUEUE_CHECK_INTERVAL_SECONDS", 30),
        scale_to_zero=_bool_value(env, "AUTOSCALING_SCALE_TO_ZERO", True),
        idle_timeout_seconds=_int_value(env, "AUTOSCALING_IDLE_TIMEOUT_SECONDS", 300),
        max_hourly_budget_usd=_float_value(env, "AUTOSCALING_MAX_HOURLY_BUDGET_USD", 1.0),
        max_daily_budget_usd=_float_value(env, "AUTOSCALING_MAX_DAILY_BUDGET_USD", 5.0),
        prefer_spot=_bool_value(env, "AUTOSCALING_PREFER_SPOT", True),
        batch_small_jobs=_bool_value(env, "AUTOSCALING_BATCH_SMALL_JOBS", True),
    )


def _rate_limit_settings(env: Mapping[str, str]) -> RateLimitSettings:
    return RateLimitSettings(
        provider=_choice(env, "RATE_LIMIT_PROVIDER", "memory", RATE_LIMIT_PROVIDERS),
        requests_per_minute=_int_value(env, "RATE_LIMIT_REQUESTS_PER_MINUTE", 60),
        burst=_int_value(env, "RATE_LIMIT_BURST", 10),
        redis_url=_env_value(env, "RATE_LIMIT_REDIS_URL", _env_value(env, "REDIS_URL", "")),
        anonymous_requests_per_minute=_int_value(env, "RATE_LIMIT_ANONYMOUS_RPM", 20),
        authenticated_requests_per_minute=_int_value(env, "RATE_LIMIT_AUTHENTICATED_RPM", 120),
        gpu_submit_requests_per_hour=_int_value(env, "RATE_LIMIT_GPU_SUBMIT_RPH", 3),
        gpu_submit_requests_per_day=_int_value(env, "RATE_LIMIT_GPU_SUBMIT_RPD", 10),
        ingestion_requests_per_hour=_int_value(env, "RATE_LIMIT_INGESTION_RPH", 10),
        training_requests_per_hour=_int_value(env, "RATE_LIMIT_TRAINING_RPH", 5),
        features_requests_per_hour=_int_value(env, "RATE_LIMIT_FEATURES_RPH", 20),
        predict_requests_per_minute=_int_value(env, "RATE_LIMIT_PREDICT_RPM", 60),
        health_requests_per_minute=_int_value(env, "RATE_LIMIT_HEALTH_RPM", 600),
    )


def _efficiency_settings(env: Mapping[str, str], base_dir: Path) -> EfficiencySettings:
    return EfficiencySettings(
        enabled=_bool_value(env, "EFFICIENCY_ENABLED", True),
        sample_rate=_float_value(env, "EFFICIENCY_SAMPLE_RATE", 1.0),
        record_memory=_bool_value(env, "EFFICIENCY_RECORD_MEMORY", True),
        record_timing=_bool_value(env, "EFFICIENCY_RECORD_TIMING", True),
        output_path=_path_value(
            env,
            "EFFICIENCY_OUTPUT_PATH",
            base_dir / "data" / "lake" / "metrics" / "efficiency.jsonl",
        ),
        report_root=_path_value(env, "EFFICIENCY_REPORT_ROOT", base_dir / "reports" / "efficiency"),
        max_pipeline_minutes_local=_float_value(env, "EFFICIENCY_MAX_PIPELINE_MINUTES_LOCAL", 30.0),
        max_peak_memory_mb=_float_value(env, "EFFICIENCY_MAX_PEAK_MEMORY_MB", 4096.0),
        min_rows_per_second=_float_value(env, "EFFICIENCY_MIN_ROWS_PER_SECOND", 10000.0),
        max_gpu_job_minutes=_float_value(env, "EFFICIENCY_MAX_GPU_JOB_MINUTES", 60.0),
        max_cost_per_run_usd=_float_value(env, "EFFICIENCY_MAX_COST_PER_RUN_USD", 2.0),
    )


def _cost_settings(env: Mapping[str, str]) -> CostGuardSettings:
    cost_mode = _choice(env, "COST_MODE", "minimum", COST_MODES)
    return CostGuardSettings(
        cost_mode=cost_mode,
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
        max_gpu_hourly_cost_usd=_float_value(
            env,
            "RUNPOD_MAX_HOURLY_COST",
            _float_value(env, "MAX_GPU_HOURLY_COST_USD", 0.75),
        ),
        require_budget_approval=_bool_value(env, "CLOUD_REQUIRE_BUDGET_APPROVAL", True),
        external_paid_api_calls_enabled=_bool_value(
            env,
            "ALLOW_EXTERNAL_PAID_API_CALLS",
            False,
        ),
        cloud_tests_enabled=_bool_value(env, "ENABLE_CLOUD_TESTS", False),
    )


def _security_settings(env: Mapping[str, str]) -> SecuritySettings:
    return SecuritySettings(
        require_secrets_for_launch=_bool_value(env, "REQUIRE_SECRETS_FOR_LAUNCH", True),
        allow_shell_commands=_bool_value(env, "ALLOW_SHELL_COMMANDS", False),
        redact_secrets=_bool_value(env, "REDACT_SECRETS", True),
        require_signed_job_manifest=_bool_value(env, "REQUIRE_SIGNED_JOB_MANIFEST", False),
        terminate_remote_on_timeout=_bool_value(env, "TERMINATE_REMOTE_ON_TIMEOUT", True),
        api_auth_enabled=_bool_value(env, "API_AUTH_ENABLED", True),
        read_only_requires_auth=_bool_value(env, "API_READ_ONLY_REQUIRES_AUTH", False),
        api_key_hashes=_api_key_hashes(env),
        cors_allowed_origins=_cors_allowed_origins(env),
        max_presigned_url_expiry_seconds=_int_value(env, "MAX_PRESIGNED_URL_EXPIRY_SECONDS", 300),
        allowed_storage_prefixes=_csv_value(env, "ALLOWED_STORAGE_PREFIXES")
        or ("data/", "datasets/", "reports/", "models/", "exports/", "logs/", "metrics/"),
        allowed_config_roots=_csv_value(env, "ALLOWED_CONFIG_ROOTS") or ("configs",),
        audit_log_path=_path_value(
            env,
            "AUDIT_LOG_PATH",
            Path("data") / "lake" / "audit" / "security_audit.jsonl",
        ),
    )


def _api_key_hashes(env: Mapping[str, str]) -> tuple[str, ...]:
    raw_keys = _csv_value(env, "API_KEYS")
    configured_hashes = _csv_value(env, "API_KEY_HASHES")
    hashed = tuple(hashlib.sha256(key.encode("utf-8")).hexdigest() for key in raw_keys if key)
    return tuple(dict.fromkeys((*configured_hashes, *hashed)))


def _cors_allowed_origins(env: Mapping[str, str]) -> tuple[str, ...]:
    origins = _csv_value(env, "CORS_ALLOWED_ORIGINS") or ("http://localhost:8000", "http://127.0.0.1:8000")
    if "*" in origins:
        raise ValueError("Invalid CORS_ALLOWED_ORIGINS '*'; configure explicit origins")
    return origins


def _deployment_mode(
    env: Mapping[str, str],
    app_env: AppEnv,
) -> DeploymentMode:
    default_mode = "cloud_mvp" if app_env == "cloud" else "onprem"
    return _choice(env, "DEPLOYMENT_MODE", default_mode, DEPLOYMENT_MODES)


def _postgres_configured(env: Mapping[str, str], deployment_mode: DeploymentMode) -> bool:
    if _env_value(env, "DATABASE_URL", ""):
        return True
    split_values = (
        _env_value(env, "POSTGRES_DB", ""),
        _env_value(env, "POSTGRES_USER", ""),
        _env_value(env, "POSTGRES_PASSWORD", ""),
        _env_value(env, "POSTGRES_HOST", ""),
    )
    if all(split_values):
        return True
    return deployment_mode == "cloud_mvp" and "DB_MODE" not in env


def _object_storage_configured(
    env: Mapping[str, str],
    deployment_mode: DeploymentMode,
) -> bool:
    if _env_value(env, "STORAGE_PROVIDER", ""):
        return True
    if _env_value(env, "OBJECT_STORAGE_BUCKET", ""):
        return True
    return deployment_mode == "cloud_mvp"


def _postgres_url(env: Mapping[str, str]) -> str:
    database_url = _env_value(env, "DATABASE_URL", "")
    if database_url:
        return database_url
    database = _env_value(env, "POSTGRES_DB", "")
    user = _env_value(env, "POSTGRES_USER", "")
    password = _env_value(env, "POSTGRES_PASSWORD", "")
    host = _env_value(env, "POSTGRES_HOST", "")
    if not all((database, user, password, host)):
        raise ValueError(
            "Invalid Postgres database settings; expected DATABASE_URL or "
            "POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_HOST"
        )
    port = _env_value(env, "POSTGRES_PORT", DEFAULT_POSTGRES_PORT)
    if not port:
        port = DEFAULT_POSTGRES_PORT
    query = _postgres_component_query(env)
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{quote(database, safe='')}"
        f"{query}"
    )


def _postgres_component_query(env: Mapping[str, str]) -> str:
    sslmode = _env_value(env, "POSTGRES_SSLMODE", "")
    if not sslmode:
        return ""
    return "?" + urlencode({"sslmode": sslmode})


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


def _int_value(env: Mapping[str, str], key: str, default_value: int) -> int:
    value = _env_value(env, key, "")
    if not value:
        return default_value
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {key} {value!r}; expected integer value") from exc


def _csv_value(env: Mapping[str, str], key: str) -> tuple[str, ...]:
    value = _env_value(env, key, "")
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


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
