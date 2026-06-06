"""ASGI rate-limit middleware with clear HTTP 429 responses."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.security.rate_limit import (
    RateLimitIdentity,
    RateLimitPolicy,
    RateLimitRequest,
    RateLimitResult,
)

ASGIApp = Callable[[dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]], Awaitable[None]]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RateLimitMiddleware:
    """ASGI middleware enforcing endpoint-aware rate limits."""

    app: ASGIApp
    policy: RateLimitPolicy

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        """Apply rate limits to HTTP scopes and pass through non-HTTP scopes."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        result = self.policy.check(rate_limit_request_from_scope(scope))
        if result.allowed:
            await self.app(scope, receive, send)
            return
        await send_rate_limit_response(send, result)


def rate_limit_request_from_scope(scope: Mapping[str, Any]) -> RateLimitRequest:
    """Build a rate-limit request from an ASGI HTTP scope."""
    headers = _headers(scope)
    api_key = headers.get("x-api-key", "")
    auth_header = headers.get("authorization", "")
    bearer_token = _bearer_token(auth_header)
    user_id = headers.get("x-user-id", "")
    client_ip = _client_ip(scope, headers)
    return RateLimitRequest(
        path=str(scope.get("path") or "/"),
        method=str(scope.get("method") or "GET"),
        identity=RateLimitIdentity(
            ip_address=client_ip,
            user_id=user_id,
            api_key=api_key or bearer_token,
            authenticated=bool(user_id or api_key or bearer_token),
        ),
        cost=_request_cost(headers),
    )


async def send_rate_limit_response(send: Send, result: RateLimitResult) -> None:
    """Send a JSON HTTP 429 response."""
    body = json.dumps(
        {
            "error": "rate_limited",
            "message": result.message or "rate limit exceeded",
            "rule": result.rule,
            "retry_after_seconds": result.retry_after_seconds,
        },
        sort_keys=True,
    ).encode("utf-8")
    headers = [(b"content-type", b"application/json")]
    headers.extend((key.encode("ascii"), value.encode("ascii")) for key, value in result.headers().items())
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": body})


def _headers(scope: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_key, raw_value in scope.get("headers", []):
        key = raw_key.decode("latin1").lower() if isinstance(raw_key, bytes) else str(raw_key).lower()
        value = raw_value.decode("latin1") if isinstance(raw_value, bytes) else str(raw_value)
        result[key] = value
    return result


def _client_ip(scope: Mapping[str, Any], headers: Mapping[str, str]) -> str:
    forwarded = headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real_ip = headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    client = scope.get("client")
    if isinstance(client, tuple) and client:
        return str(client[0])
    return "unknown"


def _bearer_token(value: str) -> str:
    prefix = "bearer "
    if value.lower().startswith(prefix):
        return value[len(prefix) :].strip()
    return ""


def _request_cost(headers: Mapping[str, str]) -> int:
    value = headers.get("x-rate-limit-cost", "")
    if not value:
        return 1
    try:
        return max(int(value), 1)
    except ValueError:
        return 1
