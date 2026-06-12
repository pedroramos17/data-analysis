"""Typed JSON responses, error envelope, and logging for the sourceflow API.

Phase 11 exposes the canonical knowledge layer over HTTP. Every endpoint must
return JSON, reasoning endpoints must carry provenance, and errors must be typed
and logged. This module centralises that contract so each view stays thin and
consistent: views raise :class:`ApiError` (or let a known domain error bubble),
and the :func:`api_endpoint` decorator turns the result into a JSON response,
maps known exceptions to typed error envelopes, and logs every call.
"""

from __future__ import annotations

import json
import logging
from functools import wraps
from typing import Any, Callable

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger("sourceflow.api")


class ApiError(Exception):
    """An error that should be returned to the client as a typed JSON envelope.

    Carrying the HTTP status and a machine-readable ``error_type`` on the
    exception keeps the failure path as explicit as the success path -- a view
    can ``raise ApiError("not found", status=404, error_type="not_found")`` and
    trust the decorator to render and log it consistently.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int = 400,
        error_type: str = "bad_request",
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.error_type = error_type
        self.details = details


def json_response(data: dict[str, Any], *, status: int = 200) -> JsonResponse:
    """Return a JSON response using Django's encoder (handles Decimal/datetime)."""
    return JsonResponse(data, status=status, encoder=DjangoJSONEncoder)


def error_response(
    message: str,
    *,
    status: int = 400,
    error_type: str = "bad_request",
    details: Any = None,
) -> JsonResponse:
    """Return the canonical typed error envelope."""
    payload: dict[str, Any] = {"error": {"type": error_type, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return json_response(payload, status=status)


def parse_json_body(request: HttpRequest) -> dict[str, Any]:
    """Parse and validate a JSON request body, raising a typed error on failure.

    An empty body is treated as ``{}`` so optional-payload POST endpoints stay
    convenient to call.
    """
    raw = request.body.decode("utf-8").strip() if request.body else ""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(
            f"request body is not valid JSON: {exc}",
            status=400,
            error_type="invalid_json",
        ) from exc
    if not isinstance(parsed, dict):
        raise ApiError(
            "request body must be a JSON object",
            status=400,
            error_type="invalid_json",
        )
    return parsed


def api_endpoint(*, methods: tuple[str, ...] = ("GET",)) -> Callable:
    """Wrap a view so it returns JSON, enforces method, and logs every call.

    Known failure shapes map to stable HTTP codes so clients can branch on them:
    missing rows -> 404, domain validation / bad input -> 422/400, and anything
    unexpected -> a logged 500 that never leaks a stack trace to the caller.
    """

    def decorator(view: Callable[..., dict[str, Any] | JsonResponse]) -> Callable:
        allowed = tuple(m.upper() for m in methods)

        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            if request.method not in allowed:
                logger.info("sourceflow.api method_not_allowed %s %s", request.method, request.path)
                return error_response(
                    f"method {request.method} not allowed; expected {', '.join(allowed)}",
                    status=405,
                    error_type="method_not_allowed",
                )
            try:
                result = view(request, *args, **kwargs)
            except ApiError as exc:
                logger.info(
                    "sourceflow.api error %s %s type=%s status=%s msg=%s",
                    request.method, request.path, exc.error_type, exc.status, exc.message,
                )
                return error_response(
                    exc.message, status=exc.status, error_type=exc.error_type, details=exc.details
                )
            except ObjectDoesNotExist as exc:
                logger.info("sourceflow.api not_found %s %s", request.method, request.path)
                return error_response(str(exc) or "resource not found", status=404, error_type="not_found")
            except (ValidationError, ValueError) as exc:
                logger.info("sourceflow.api unprocessable %s %s msg=%s", request.method, request.path, exc)
                return error_response(str(exc), status=422, error_type="unprocessable_entity")
            except Exception:  # noqa: BLE001 - last-resort handler, logged with stack
                logger.exception("sourceflow.api unhandled %s %s", request.method, request.path)
                return error_response(
                    "internal server error", status=500, error_type="internal_error"
                )
            if isinstance(result, JsonResponse):
                return result
            logger.info("sourceflow.api ok %s %s", request.method, request.path)
            return json_response(result)

        # The knowledge API is consumed by programmatic clients, so it is
        # CSRF-exempt; authentication/authorization is a separate concern that
        # later phases can layer on (e.g. API keys) without touching each view.
        return csrf_exempt(wrapper)

    return decorator
