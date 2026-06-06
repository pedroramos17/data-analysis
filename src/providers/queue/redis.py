"""Redis queue provider boundary."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from src.config.settings import QueueSettings
from src.providers.base import MissingProviderDependencyError, ProviderError
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
        message_id = f"redis-{uuid.uuid4().hex}"
        message = json.dumps(
            {"message_id": message_id, "topic": topic, "payload": dict(payload)},
            sort_keys=True,
        )
        client.rpush(topic, message)
        return message_id

    def consume(self, topic: str, handler: QueueHandler) -> int:
        """Drain available Redis list items synchronously."""
        client = self._client()
        count = 0
        while item := client.lpop(topic):
            envelope = _decode_message(item)
            message_id = str(envelope.get("message_id", ""))
            if message_id:
                client.hset(
                    _inflight_key(),
                    message_id,
                    json.dumps(envelope, sort_keys=True),
                )
            handler(dict(envelope.get("payload", {})))
            if message_id:
                self.ack(message_id)
            count += 1
        return count

    def ack(self, message_id: str) -> bool:
        """Acknowledge a Redis message id."""
        return bool(self._client().hdel(_inflight_key(), message_id) > 0)

    def retry(self, message_id: str) -> bool:
        """Requeue a Redis message id from the in-flight hash."""
        client = self._client()
        raw = client.hget(_inflight_key(), message_id)
        if raw is None:
            return False
        envelope = _decode_message(raw)
        client.rpush(
            str(envelope.get("topic", _retry_topic())),
            json.dumps(envelope, sort_keys=True),
        )
        client.hdel(_inflight_key(), message_id)
        return True

    def dead_letter(self, message_id: str) -> bool:
        """Move a Redis message id to the dead-letter list."""
        client = self._client()
        raw = client.hget(_inflight_key(), message_id)
        if raw is None:
            return False
        client.rpush(_dead_letter_topic(), _decode_redis_item(raw))
        client.hdel(_inflight_key(), message_id)
        return True

    def healthcheck(self) -> bool:
        """Return whether Redis responds to ping."""
        return bool(self._client().ping())

    def _client(self) -> object:
        if not self.settings.connection_url:
            raise ProviderError(
                "REDIS_URL or QUEUE_URL is required when QUEUE_PROVIDER=redis"
            )
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


def _decode_message(item: object) -> dict[str, object]:
    payload = json.loads(_decode_redis_item(item))
    if isinstance(payload, dict) and "payload" in payload:
        return payload
    return {"message_id": "", "payload": payload if isinstance(payload, dict) else {}}


def _inflight_key() -> str:
    return "queue:inflight"


def _retry_topic() -> str:
    return "queue:retry"


def _dead_letter_topic() -> str:
    return "queue:dead_letter"
