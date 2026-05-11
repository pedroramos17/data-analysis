"""Django app configuration for monitoring."""

from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    """Configure monitoring models and admin labels.

    Example:
        Django loads this config from `INSTALLED_APPS`.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "monitoring"
    verbose_name = "Public Source Monitoring"

    def ready(self) -> None:
        """Register local database connection tuning.

        Example:
            Django calls this once when the app registry is ready.
        """
        from monitoring.sqlite import register_sqlite_pragmas

        register_sqlite_pragmas()
