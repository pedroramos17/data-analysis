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
    _inflight: dict[str, dict[str, object]] = field(default_factory=dict)
    _acked: set[str] = field(default_factory=set)
    _dead_letters: dict[str, dict[str, object]] = field(default_factory=dict)
    _counter: itertools.count = field(default_factory=lambda: itertools.count(1))

    def publish(self, topic: str, payload: Mapping[str, object]) -> str:
        """Publish one local message."""
        message_id = f"local-{next(self._counter)}"
        message = {"message_id": message_id, "payload": dict(payload)}
        self._messages.setdefault(topic, []).append(message)
        return message_id

    def consume(self, topic: str, handler: QueueHandler) -> int:
        """Consume local messages synchronously."""
        messages = self._messages.get(topic, [])
        count = 0
        while messages:
            message = messages.pop(0)
            message_id = str(message["message_id"])
            self._inflight[message_id] = {"topic": topic, **message}
            handler(message["payload"])
            self.ack(message_id)
            count += 1
        self._messages.pop(topic, None)
        return count

    def ack(self, message_id: str) -> bool:
        """Acknowledge a local message id."""
        self._inflight.pop(message_id, None)
        self._acked.add(message_id)
        return True

    def retry(self, message_id: str) -> bool:
        """Requeue an in-flight local message."""
        message = self._inflight.pop(message_id, None)
        if message is None:
            return False
        topic = str(message.get("topic", ""))
        self._messages.setdefault(topic, []).append(
            {"message_id": message_id, "payload": dict(message.get("payload", {}))}
        )
        return True

    def dead_letter(self, message_id: str) -> bool:
        """Move an in-flight local message to dead letters."""
        message = self._inflight.pop(message_id, None)
        if message is None:
            return False
        self._dead_letters[message_id] = message
        return True

    def healthcheck(self) -> bool:
        """Return whether the local in-memory queue is usable."""
        return True
