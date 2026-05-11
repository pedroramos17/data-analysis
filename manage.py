#!/usr/bin/env python
"""Django command entrypoint."""

import os
import sys


def main() -> None:
    """Run Django management commands.

    Example:
        `python manage.py migrate`
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "public_monitor.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
