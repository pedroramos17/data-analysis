"""SQLite connection pragmas for local dashboard workflows."""

from django.db.backends.signals import connection_created


def configure_sqlite_connection(
    sender: object, connection: object, **kwargs: object
) -> None:
    """Apply pragmatic SQLite settings for local concurrent reads/writes.

    Example:
        Django calls this after opening a SQLite connection.
    """
    if getattr(connection, "vendor", "") != "sqlite":
        return
    cursor = connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")


def register_sqlite_pragmas() -> None:
    """Register the SQLite connection handler once during app startup.

    Example:
        `register_sqlite_pragmas()`
    """
    connection_created.connect(
        configure_sqlite_connection,
        dispatch_uid="monitoring.sqlite_pragmas",
    )
