"""Phase 11 API and job-submission rate-limit tests."""

from __future__ import annotations

import asyncio
import json
import unittest

from src.config.settings import load_runtime_settings
from src.middleware.rate_limit import RateLimitMiddleware
from src.providers.base import ProviderError
from src.security.rate_limit import (
    MemoryRateLimitStore,
    RateLimitIdentity,
    RateLimitPolicy,
    RateLimitRequest,
    RedisRateLimitStore,
    endpoint_for_path,
    rate_limit_settings_from_config,
)


class Phase11RateLimitTests(unittest.TestCase):
    """Rate limiting must protect GPU submit and work locally without Redis."""

    def test_default_rate_limit_settings_parse_env(self) -> None:
        settings = load_runtime_settings(
            env={
                "RATE_LIMIT_PROVIDER": "memory",
                "RATE_LIMIT_ANONYMOUS_RPM": "20",
                "RATE_LIMIT_AUTHENTICATED_RPM": "120",
                "RATE_LIMIT_GPU_SUBMIT_RPH": "3",
                "RATE_LIMIT_GPU_SUBMIT_RPD": "10",
                "RATE_LIMIT_INGESTION_RPH": "10",
                "RATE_LIMIT_TRAINING_RPH": "5",
            }
        ).rate_limit

        self.assertEqual(settings.provider, "memory")
        self.assertEqual(settings.anonymous_requests_per_minute, 20)
        self.assertEqual(settings.authenticated_requests_per_minute, 120)
        self.assertEqual(settings.gpu_submit_requests_per_hour, 3)
        self.assertEqual(settings.gpu_submit_requests_per_day, 10)
        self.assertEqual(settings.ingestion_requests_per_hour, 10)
        self.assertEqual(settings.training_requests_per_hour, 5)

    def test_rate_limit_settings_parse_nested_config(self) -> None:
        settings = rate_limit_settings_from_config(
            {
                "rate_limits": {
                    "anonymous": {"requests_per_minute": 20},
                    "authenticated": {"requests_per_minute": 120},
                    "gpu_submit": {"requests_per_hour": 3, "requests_per_day": 10},
                    "ingestion": {"requests_per_hour": 10},
                    "training": {"requests_per_hour": 5},
                }
            }
        )

        self.assertEqual(settings.anonymous_requests_per_minute, 20)
        self.assertEqual(settings.authenticated_requests_per_minute, 120)
        self.assertEqual(settings.gpu_submit_requests_per_hour, 3)
        self.assertEqual(settings.gpu_submit_requests_per_day, 10)

    def test_local_memory_provider_works_without_redis(self) -> None:
        settings = load_runtime_settings(env={"RATE_LIMIT_PROVIDER": "memory"}).rate_limit
        policy = RateLimitPolicy(settings)

        result = policy.check(_request("/health", ip="127.0.0.1"), now=0)

        self.assertTrue(result.allowed)
        self.assertEqual(result.provider, "memory")

    def test_per_ip_limit_blocks_anonymous_requests(self) -> None:
        settings = load_runtime_settings(env={"RATE_LIMIT_ANONYMOUS_RPM": "1"}).rate_limit
        policy = RateLimitPolicy(settings, MemoryRateLimitStore())

        first = policy.check(_request("/predict", ip="10.0.0.1"), now=0)
        second = policy.check(_request("/predict", ip="10.0.0.1"), now=1)

        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.rule, "anonymous")

    def test_per_user_api_key_limit_blocks_authenticated_requests(self) -> None:
        settings = load_runtime_settings(env={"RATE_LIMIT_AUTHENTICATED_RPM": "1"}).rate_limit
        policy = RateLimitPolicy(settings, MemoryRateLimitStore())
        first_identity = RateLimitIdentity(ip_address="10.0.0.1", api_key="key-1", authenticated=True)
        second_identity = RateLimitIdentity(ip_address="10.0.0.2", api_key="key-1", authenticated=True)

        first = policy.check(RateLimitRequest("/health", identity=first_identity), now=0)
        second = policy.check(RateLimitRequest("/health", identity=second_identity), now=1)

        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual(second.rule, "authenticated")

    def test_per_endpoint_ingestion_limit_blocks(self) -> None:
        settings = load_runtime_settings(
            env={"RATE_LIMIT_ANONYMOUS_RPM": "100", "RATE_LIMIT_INGESTION_RPH": "1"}
        ).rate_limit
        policy = RateLimitPolicy(settings, MemoryRateLimitStore())

        first = policy.check(_request("/ingest/run", ip="10.0.0.2"), now=0)
        second = policy.check(_request("/ingest/run", ip="10.0.0.2"), now=1)

        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual(second.rule, "ingestion")

    def test_gpu_submit_cost_sensitive_limit_blocks_submission(self) -> None:
        settings = load_runtime_settings(
            env={
                "RATE_LIMIT_ANONYMOUS_RPM": "100",
                "RATE_LIMIT_GPU_SUBMIT_RPH": "3",
                "RATE_LIMIT_GPU_SUBMIT_RPD": "10",
            }
        ).rate_limit
        policy = RateLimitPolicy(settings, MemoryRateLimitStore())

        first = policy.check(_request("/compute/runpod/submit", ip="10.0.0.3", cost=2), now=0)
        second = policy.check(_request("/compute/runpod/submit", ip="10.0.0.3", cost=2), now=1)

        self.assertTrue(first.allowed)
        self.assertFalse(second.allowed)
        self.assertEqual(second.rule, "gpu_submit")

    def test_endpoint_mapping_for_required_routes(self) -> None:
        self.assertEqual(endpoint_for_path("/ingest/run"), "ingestion")
        self.assertEqual(endpoint_for_path("/features/build"), "features")
        self.assertEqual(endpoint_for_path("/train/run"), "training")
        self.assertEqual(endpoint_for_path("/compute/runpod/submit"), "gpu_submit")
        self.assertEqual(endpoint_for_path("/predict"), "predict")
        self.assertEqual(endpoint_for_path("/health"), "health")

    def test_redis_provider_requires_url_when_used(self) -> None:
        store = RedisRateLimitStore("")

        with self.assertRaisesRegex(ProviderError, "RATE_LIMIT_REDIS_URL"):
            store.increment("x", 60, 1, 1, 0)

    def test_middleware_returns_clear_429_response(self) -> None:
        settings = load_runtime_settings(
            env={"RATE_LIMIT_ANONYMOUS_RPM": "100", "RATE_LIMIT_GPU_SUBMIT_RPH": "1"}
        ).rate_limit
        middleware = RateLimitMiddleware(_ok_app, RateLimitPolicy(settings, MemoryRateLimitStore()))
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/compute/runpod/submit",
            "client": ("10.0.0.4", 1234),
            "headers": [],
        }

        first = asyncio.run(_call_app(middleware, scope))
        second = asyncio.run(_call_app(middleware, scope))

        self.assertEqual(first[0]["status"], 200)
        self.assertEqual(second[0]["status"], 429)
        headers = dict(second[0]["headers"])
        self.assertIn(b"Retry-After", headers)
        body = json.loads(second[1]["body"].decode("utf-8"))
        self.assertEqual(body["error"], "rate_limited")
        self.assertEqual(body["rule"], "gpu_submit")


def _request(path: str, *, ip: str, cost: int = 1) -> RateLimitRequest:
    return RateLimitRequest(path=path, identity=RateLimitIdentity(ip_address=ip), cost=cost)


async def _ok_app(scope: dict[str, object], receive: object, send: object) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _call_app(app: RateLimitMiddleware, scope: dict[str, object]) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    return messages


if __name__ == "__main__":
    unittest.main()
