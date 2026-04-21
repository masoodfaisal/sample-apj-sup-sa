"""FastAPI app entrypoint for the gateway/admin service."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from gateway.core.config import Settings, get_settings
from gateway.core.database import ENGINE, READ_ENGINE
from gateway.core.exceptions import register_exception_handlers
from gateway.core.middleware import AdminOriginMiddleware, RequestIdMiddleware
from gateway.core.telemetry import init_meter_provider
from gateway.domains.admin.router import router as admin_router
from gateway.domains.auth.router import router as auth_router
from gateway.domains.runtime.router import router as runtime_router
from gateway.domains.sync.router import router as sync_router


def _resolve_log_level(raw_level: str) -> int:
    if raw_level.isdigit():
        return int(raw_level)
    return logging.getLevelNamesMapping().get(raw_level.upper(), logging.INFO)


def configure_logging(settings: Settings) -> None:
    """Attach gateway loggers to the active process handlers."""

    uvicorn_logger = logging.getLogger("uvicorn")
    root_logger = logging.getLogger()
    gateway_logger = logging.getLogger("gateway")
    handlers = list(uvicorn_logger.handlers) or list(root_logger.handlers)

    if not handlers:
        fallback_handler = logging.StreamHandler()
        fallback_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        handlers = [fallback_handler]

    gateway_logger.handlers = handlers
    gateway_logger.setLevel(_resolve_log_level(settings.log_level))
    gateway_logger.propagate = False


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    try:
        yield
    finally:
        await READ_ENGINE.dispose()
        await ENGINE.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    init_meter_provider(settings.otlp_endpoint, settings.otlp_export_interval_millis)
    app = FastAPI(title=settings.app_name, lifespan=app_lifespan)
    app.add_middleware(AdminOriginMiddleware, settings=settings)
    app.add_middleware(RequestIdMiddleware, settings=settings)
    register_exception_handlers(app)
    app.include_router(runtime_router)
    app.include_router(admin_router)
    app.include_router(auth_router)
    app.include_router(sync_router)
    return app


app = create_app()
