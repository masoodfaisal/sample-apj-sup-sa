"""Async database primitives for the gateway app."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from gateway.core.config import get_settings


def create_engine() -> AsyncEngine:
    """Build the shared async SQLAlchemy engine."""

    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def create_read_engine() -> AsyncEngine:
    """Build the read-only async SQLAlchemy engine for Aurora reader."""

    settings = get_settings()
    return create_async_engine(settings.read_database_url, pool_pre_ping=True)


ENGINE = create_engine()
READ_ENGINE = create_read_engine()
SessionFactory = async_sessionmaker(ENGINE, expire_on_commit=False, class_=AsyncSession)
ReadSessionFactory = async_sessionmaker(READ_ENGINE, expire_on_commit=False, class_=AsyncSession)
