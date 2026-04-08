"""Middleware used by the gateway application."""

from __future__ import annotations

import hmac
import logging
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from gateway.core.config import Settings

logger = logging.getLogger(__name__)


def _ensure_request_id(request: Request, header_name: str) -> str:
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return request_id

    request_id = request.headers.get(header_name) or f"req_{uuid4().hex}"
    request.state.request_id = request_id
    return request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Propagate or create request IDs."""

    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        request_id = _ensure_request_id(request, self._settings.request_id_header)
        response = await call_next(request)
        response.headers[self._settings.request_id_header] = request_id
        return response


class AdminOriginMiddleware(BaseHTTPMiddleware):
    """Reject admin requests that did not arrive through the trusted origin."""

    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._settings = settings

    def _forbidden_response(self, code: str, request_id: str) -> JSONResponse:
        response = JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": code,
                    "message": "Forbidden",
                    "request_id": request_id,
                    "retryable": False,
                }
            },
        )
        response.headers[self._settings.request_id_header] = request_id
        return response

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        if not self._settings.admin_origin_enforce:
            return await call_next(request)
        request_id = _ensure_request_id(request, self._settings.request_id_header)
        if request.url.path.startswith("/v1/admin"):
            origin = request.headers.get(self._settings.admin_origin_header) or ""
            if not hmac.compare_digest(origin, self._settings.admin_origin_value):
                logger.warning(
                    "admin origin rejected request_id=%s path=%s",
                    request_id,
                    request.url.path,
                )
                return self._forbidden_response("admin_origin_invalid", request_id)
        if request.url.path.startswith("/v1/auth"):
            origin = request.headers.get(self._settings.auth_origin_header) or ""
            if not hmac.compare_digest(origin, self._settings.auth_origin_value):
                logger.warning(
                    "auth origin rejected request_id=%s path=%s",
                    request_id,
                    request.url.path,
                )
                return self._forbidden_response("auth_origin_invalid", request_id)
        return await call_next(request)
