"""Redis queue provider boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from src.config.settings import QueueSettings
from src.providers.base import MissingProviderDependencyError
from src.providers.queue.base import QueueHandler


@dataclass(frozen=True, slots=True)
class RedisQueueProvider:
    """Redis-backed queue provider.

    Example:
        `RedisQueueProvider(settings).healthcheck()`
    """

    settings: QueueSettings

    def publish(self, topic: str, payload: Mapping[str, object]) -> str:
        """Publish JSON to a Redis list."""
        client = self._client()
        message = json.dumps(dict(payload), sort_keys=True)
        return str(client.rpush(topic, message))

    def consume(self, topic: str, handler: QueueHandler) -> int:
        """Drain available Redis list items synchronously."""
        client = self._client()
        count = 0
        while item := client.lpop(topic):
            handler(json.loads(_decode_redis_item(item)))
            count += 1
        return count

    def healthcheck(self) -> bool:
        """Return whether Redis responds to ping."""
        return bool(self._client().ping())

    def _client(self) -> object:
        redis = _redis_module()
        return redis.Redis.from_url(self.settings.connection_url)


def _redis_module() -> object:
    try:
        import redis
    except ImportError as exc:
        raise MissingProviderDependencyError(
            "redis is required by Redis queue provider; expected installed module"
        ) from exc
    return redis


def _decode_redis_item(item: object) -> str:
    if isinstance(item, bytes):
        return item.decode("utf-8")
    return str(item)
