"""Structured logging helpers for ingestion and export jobs."""

import json
import logging
from datetime import date, datetime
from typing import override


class JsonLineFormatter(logging.Formatter):
    """Format log records as single-line JSON.

    Example:
        `handler.setFormatter(JsonLineFormatter())`
    """

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON object encoded as a line.

        Example:
            `formatter.format(record)`
        """
        payload = self._base_payload(record)
        payload.update(self._extra_payload(record))
        return json.dumps(payload, default=_json_default, sort_keys=True)

    def _base_payload(self, record: logging.LogRecord) -> dict[str, object]:
        return {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
        }

    def _extra_payload(self, record: logging.LogRecord) -> dict[str, object]:
        reserved = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
        return {
            key: value
            for key, value in record.__dict__.items()
            if key not in reserved and not key.startswith("_")
        }


def _json_default(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)
