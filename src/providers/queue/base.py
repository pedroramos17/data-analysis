"""Queue provider interface."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

QueueHandler = Callable[[Mapping[str, object]], None]


class QueueProvider(Protocol):
    """Messaging boundary for local and cloud workers.

    Example:
        `queue.publish("jobs", {"id": "1"})`
    """

    def publish(self, topic: str, payload: Mapping[str, object]) -> str:
        """Publish one payload and return a message id."""

    def consume(self, topic: str, handler: QueueHandler) -> int:
        """Consume pending messages and return handled count."""

    def ack(self, message_id: str) -> bool:
        """Acknowledge a message id."""

    def retry(self, message_id: str) -> bool:
        """Retry a message id when the provider can requeue it."""

    def dead_letter(self, message_id: str) -> bool:
        """Move a message id to the provider dead-letter store."""

    def healthcheck(self) -> bool:
        """Return whether the queue provider is reachable."""
