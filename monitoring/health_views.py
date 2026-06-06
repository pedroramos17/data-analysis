"""Lightweight health and metrics endpoints for container deployments."""

from __future__ import annotations

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse


def healthz(request: HttpRequest) -> JsonResponse:
    """Return application and database health for Docker health checks."""
    database_ok = _database_healthcheck()
    status_code = 200 if database_ok else 503
    return JsonResponse(
        {
            "status": "ok" if database_ok else "degraded",
            "database": database_ok,
            "app_env": getattr(settings, "APP_ENV", "local"),
            "deployment_mode": getattr(settings, "DEPLOYMENT_MODE", "onprem"),
            "db_mode": getattr(settings, "DB_MODE", "sqlite"),
            "storage_provider": getattr(settings, "STORAGE_PROVIDER", "local"),
        },
        status=status_code,
    )


def metrics(request: HttpRequest) -> HttpResponse:
    """Return minimal Prometheus-compatible process metadata."""
    database_ok = 1 if _database_healthcheck() else 0
    db_mode = getattr(settings, "DB_MODE", "sqlite")
    body = "\n".join(
        [
            "# HELP app_health Database-backed app health status.",
            "# TYPE app_health gauge",
            f"app_health{{db_mode=\"{db_mode}\"}} {database_ok}",
            "",
        ]
    )
    return HttpResponse(body, content_type="text/plain; version=0.0.4")


def _database_healthcheck() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("select 1")
            return cursor.fetchone() == (1,)
    except Exception:
        return False
