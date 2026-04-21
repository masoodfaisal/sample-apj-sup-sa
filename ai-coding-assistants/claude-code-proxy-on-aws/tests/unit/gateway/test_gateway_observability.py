"""Tests for gateway logging and request tracing behavior."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from gateway.core.config import Settings, get_settings
from gateway.core.exceptions import ConflictError, NotFoundError, register_exception_handlers
from gateway.core.middleware import AdminOriginMiddleware, RequestIdMiddleware
from shared.exceptions import AuthenticationError, KeyExpiredError, UserInactiveError


def _restore_logger_state(
    logger: logging.Logger,
    *,
    handlers: list[logging.Handler],
    level: int,
    propagate: bool,
) -> None:
    logger.handlers = handlers
    logger.setLevel(level)
    logger.propagate = propagate


@pytest.fixture(autouse=True)
def _isolate_gateway_logging() -> None:
    gateway_logger = logging.getLogger("gateway")
    original = {
        "handlers": list(gateway_logger.handlers),
        "level": gateway_logger.level,
        "propagate": gateway_logger.propagate,
    }
    gateway_logger.handlers = []
    gateway_logger.setLevel(logging.NOTSET)
    gateway_logger.propagate = True
    try:
        yield
    finally:
        _restore_logger_state(gateway_logger, **original)


def test_configure_logging_uses_uvicorn_handlers_and_env_level() -> None:
    from gateway.main import configure_logging

    uvicorn_logger = logging.getLogger("uvicorn")
    gateway_logger = logging.getLogger("gateway")
    original_uvicorn = {
        "handlers": list(uvicorn_logger.handlers),
        "level": uvicorn_logger.level,
        "propagate": uvicorn_logger.propagate,
    }
    original_gateway = {
        "handlers": list(gateway_logger.handlers),
        "level": gateway_logger.level,
        "propagate": gateway_logger.propagate,
    }
    handler = logging.StreamHandler()

    try:
        uvicorn_logger.handlers = [handler]
        gateway_logger.handlers = []
        gateway_logger.setLevel(logging.NOTSET)
        gateway_logger.propagate = True

        configure_logging(Settings(log_level="DEBUG"))

        assert gateway_logger.handlers == [handler]
        assert gateway_logger.level == logging.DEBUG
        assert gateway_logger.propagate is False
    finally:
        _restore_logger_state(uvicorn_logger, **original_uvicorn)
        _restore_logger_state(gateway_logger, **original_gateway)


def test_get_settings_reads_log_level_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.log_level == "DEBUG"
    finally:
        get_settings.cache_clear()


def test_get_settings_reads_virtual_key_ttl_from_env(monkeypatch) -> None:
    monkeypatch.setenv("VIRTUAL_KEY_TTL_MS", "6000")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.virtual_key_ttl_ms == 6000
    finally:
        get_settings.cache_clear()


def test_settings_reject_negative_virtual_key_ttl() -> None:
    with pytest.raises(ValueError, match="VIRTUAL_KEY_TTL_MS must be greater than or equal to 0"):
        Settings(virtual_key_ttl_ms=-1)


def _build_test_app() -> FastAPI:
    app = FastAPI()
    settings = Settings()
    app.add_middleware(AdminOriginMiddleware, settings=settings)
    app.add_middleware(RequestIdMiddleware, settings=settings)
    register_exception_handlers(app)

    @app.get("/v1/admin/ping")
    async def admin_ping() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/v1/admin/not-found")
    async def admin_not_found() -> dict[str, bool]:
        raise NotFoundError("Team not found", code="team_not_found")

    @app.get("/v1/admin/conflict")
    async def admin_conflict() -> dict[str, bool]:
        raise ConflictError("Team already exists", code="team_exists")

    @app.get("/v1/auth/inactive")
    async def auth_inactive() -> dict[str, bool]:
        raise UserInactiveError("User is not active")

    @app.get("/v1/auth/failed")
    async def auth_failed() -> dict[str, bool]:
        raise AuthenticationError("Authentication failed")

    @app.get("/v1/auth/expired")
    async def auth_expired() -> dict[str, bool]:
        raise KeyExpiredError("Virtual Key expired")

    @app.get("/runtime-inactive")
    async def runtime_inactive() -> dict[str, bool]:
        raise UserInactiveError("User is not active")

    @app.get("/runtime-expired")
    async def runtime_expired() -> dict[str, bool]:
        raise KeyExpiredError("Virtual Key expired")

    @app.get("/boom")
    async def boom() -> dict[str, bool]:
        raise RuntimeError("boom")

    return app


def test_admin_origin_rejection_includes_request_id_and_logs(caplog) -> None:
    client = TestClient(_build_test_app())

    with caplog.at_level(logging.WARNING, logger="gateway.core.middleware"):
        response = client.get("/v1/admin/ping")

    assert response.status_code == 403
    request_id = response.headers["x-request-id"]
    body = response.json()
    assert body["error"]["code"] == "admin_origin_invalid"
    assert body["error"]["request_id"] == request_id
    assert f"request_id={request_id}" in caplog.text
    assert "admin origin rejected" in caplog.text


def test_unexpected_error_logs_traceback_with_request_id(caplog) -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR, logger="gateway.core.exceptions"):
        response = client.get("/boom", headers={"x-request-id": "req-boom"})

    assert response.status_code == 500
    assert response.json()["request_id"] == "req-boom"

    matching_records = [
        record
        for record in caplog.records
        if record.name == "gateway.core.exceptions"
        and record.message.startswith("Unhandled exception")
    ]
    assert matching_records
    assert "request_id=req-boom" in matching_records[-1].message
    assert "path=/boom" in matching_records[-1].message
    assert matching_records[-1].exc_info is not None


def test_admin_not_found_returns_404_admin_envelope() -> None:
    client = TestClient(_build_test_app())

    response = client.get(
        "/v1/admin/not-found",
        headers={"x-admin-origin": "apigw", "x-request-id": "req-admin-404"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "team_not_found",
            "message": "Team not found",
            "request_id": "req-admin-404",
            "retryable": False,
        }
    }


def test_admin_conflict_returns_409_admin_envelope() -> None:
    client = TestClient(_build_test_app())

    response = client.get(
        "/v1/admin/conflict",
        headers={"x-admin-origin": "apigw", "x-request-id": "req-admin-409"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "team_exists",
            "message": "Team already exists",
            "request_id": "req-admin-409",
            "retryable": False,
        }
    }


def test_auth_user_inactive_returns_409_admin_envelope() -> None:
    client = TestClient(_build_test_app())

    response = client.get(
        "/v1/auth/inactive",
        headers={"x-auth-origin": "apigw", "x-request-id": "req-auth-409"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "user_inactive",
            "message": "User is not active",
            "request_id": "req-auth-409",
            "retryable": False,
        }
    }


def test_authentication_failure_returns_401_admin_envelope() -> None:
    client = TestClient(_build_test_app())

    response = client.get(
        "/v1/auth/failed",
        headers={"x-auth-origin": "apigw", "x-request-id": "req-auth-401"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "authentication_failed",
            "message": "Authentication failed",
            "request_id": "req-auth-401",
            "retryable": False,
        }
    }


def test_auth_expired_returns_401_admin_envelope() -> None:
    client = TestClient(_build_test_app())

    response = client.get(
        "/v1/auth/expired",
        headers={"x-auth-origin": "apigw", "x-request-id": "req-auth-expired"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "virtual_key_expired",
            "message": "Virtual Key expired",
            "request_id": "req-auth-expired",
            "retryable": False,
        }
    }


def test_runtime_user_inactive_still_returns_runtime_envelope() -> None:
    client = TestClient(_build_test_app())

    response = client.get("/runtime-inactive", headers={"x-request-id": "req-runtime-403"})

    assert response.status_code == 403
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "permission_error",
            "message": "User is not active",
        },
        "request_id": "req-runtime-403",
    }


def test_runtime_expired_still_returns_runtime_envelope() -> None:
    client = TestClient(_build_test_app())

    response = client.get("/runtime-expired", headers={"x-request-id": "req-runtime-expired"})

    assert response.status_code == 401
    assert response.json() == {
        "type": "error",
        "error": {
            "type": "authentication_error",
            "message": "Virtual Key expired",
        },
        "request_id": "req-runtime-expired",
    }
