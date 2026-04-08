"""Helpers for migration database connections."""

from __future__ import annotations

import os

from sqlalchemy.engine import URL, make_url


def build_migration_database_url(
    username: str,
    password: str,
    host: str,
    *,
    port: int = 5432,
    database: str = "claude_proxy",
) -> str:
    """Build the sync SQLAlchemy URL used by the migration Lambda."""

    return URL.create(
        "postgresql+pg8000",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    ).render_as_string(hide_password=False)


def build_connect_args(database_url: str | None) -> dict[str, object]:
    """Return DBAPI-specific connect args for Alembic engines."""

    if not database_url:
        return {}

    if os.getenv("MIGRATION_DISABLE_SSL", "").lower() == "true":
        return {}

    if make_url(database_url).drivername == "postgresql+pg8000":
        return {"ssl_context": True}

    return {}
