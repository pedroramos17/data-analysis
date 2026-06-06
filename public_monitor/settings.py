"""Django settings for public source monitoring."""

import os
from pathlib import Path

from public_monitor.remote_mobile import (
    build_remote_mobile_settings,
    warn_remote_mobile_testing,
)
from src.config.settings import load_runtime_settings

BASE_DIR = Path(__file__).resolve().parent.parent
RUNTIME_SETTINGS = load_runtime_settings(base_dir=BASE_DIR)

SECRET_KEY = "dev-only-public-source-monitor"
DEBUG = True
BASE_ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]
REMOTE_MOBILE_SETTINGS = build_remote_mobile_settings(DEBUG, BASE_ALLOWED_HOSTS)
ALLOWED_HOSTS: list[str] = REMOTE_MOBILE_SETTINGS.allowed_hosts
CSRF_TRUSTED_ORIGINS: list[str] = REMOTE_MOBILE_SETTINGS.csrf_trusted_origins
REMOTE_MOBILE_TESTING_ENABLED = REMOTE_MOBILE_SETTINGS.enabled
DEV_PUBLIC_BASE_URL = REMOTE_MOBILE_SETTINGS.public_base_url
DEV_EXTRA_ALLOWED_HOSTS = REMOTE_MOBILE_SETTINGS.extra_allowed_hosts
DEV_CSRF_TRUSTED_ORIGINS = REMOTE_MOBILE_SETTINGS.csrf_trusted_origins
DEV_TUNNEL_PROVIDER = REMOTE_MOBILE_SETTINGS.provider
DEV_TUNNEL_NOTES = REMOTE_MOBILE_SETTINGS.notes
warn_remote_mobile_testing(REMOTE_MOBILE_SETTINGS)

def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name, "")
    if not value.strip():
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-public-source-monitor")
DEBUG = _env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS: list[str] = _env_list(
    "DJANGO_ALLOWED_HOSTS",
    ["localhost", "127.0.0.1", "testserver"],
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "monitoring.apps.MonitoringConfig",
    "quant4.apps.Quant4Config",
    "quantspace.apps.QuantspaceConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "public_monitor.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "monitoring.context_processors.remote_mobile_testing",
            ],
        },
    }
]

WSGI_APPLICATION = "public_monitor.wsgi.application"

DATABASES = {"default": RUNTIME_SETTINGS.database.as_django_database()}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "media/"

RAW_SNAPSHOT_DIR = MEDIA_ROOT / "raw"
PARQUET_EXPORT_DIR = BASE_DIR / "exports"
MONITOR_USER_AGENT = "PublicSourceMonitor/0.1 (+https://example.local/contact)"
MONITOR_AUTOLOAD_CATALOGS = False

APP_ENV = RUNTIME_SETTINGS.app_env
DEPLOYMENT_MODE = RUNTIME_SETTINGS.deployment_mode
DB_MODE = RUNTIME_SETTINGS.database.db_mode
OLAP_MODE = RUNTIME_SETTINGS.duckdb.olap_mode
STORAGE_PROVIDER = RUNTIME_SETTINGS.storage.provider
QUEUE_PROVIDER = RUNTIME_SETTINGS.queue.provider
SECRETS_PROVIDER = RUNTIME_SETTINGS.secrets_provider
MODEL_PROVIDER = RUNTIME_SETTINGS.model.provider
COMPUTE_PROVIDER = RUNTIME_SETTINGS.compute.provider
ORCHESTRATOR = RUNTIME_SETTINGS.pipeline.orchestrator
RATE_LIMIT_PROVIDER = RUNTIME_SETTINGS.rate_limit.provider
MODEL_DEVICE = RUNTIME_SETTINGS.pipeline.model_device
COST_MODE = RUNTIME_SETTINGS.pipeline.cost_mode
RUNPOD_DRY_RUN = RUNTIME_SETTINGS.runpod.dry_run
DATA_LAKE_DIR = RUNTIME_SETTINGS.duckdb.data_lake_root
DUCKDB_PATH = RUNTIME_SETTINGS.duckdb.database_path
MODEL_CACHE_DIR = RUNTIME_SETTINGS.model.cache_root

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "monitoring.logging.JsonLineFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "monitoring": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
