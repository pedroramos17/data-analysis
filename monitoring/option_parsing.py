"""Small helpers for management command option values."""


def optional_int(value: object) -> int | None:
    """Convert a command option to an optional integer.

    Example:
        `optional_int("10")`
    """
    if value is None:
        return None
    return int(value)
