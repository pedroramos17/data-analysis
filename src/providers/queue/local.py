"""Local in-memory queue provider."""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.providers.queue.base import QueueHandler


@dataclass(slots=True)
class LocalQueueProvider:
    """In-memory queue for local tests and synchronous MVP workflows.

    Example:
        `LocalQueueProvider().publish("jobs", {"id": 1})`
    """

    _messages: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    _counter: itertools.count = field(default_factory=lambda: itertools.count(1))

    def publish(self, topic: str, payload: Mapping[str, object]) -> str:
        """Publish one local message."""
        message_id = f"local-{next(self._counter)}"
        message = {"message_id": message_id, "payload": dict(payload)}
        self._messages.setdefault(topic, []).append(message)
        return message_id

    def consume(self, topic: str, handler: QueueHandler) -> int:
        """Consume local messages synchronously."""
        messages = self._messages.pop(topic, [])
        for message in messages:
            handler(message["payload"])
        return len(messages)

    def healthcheck(self) -> bool:
        """Return whether the local in-memory queue is usable."""
        return True
