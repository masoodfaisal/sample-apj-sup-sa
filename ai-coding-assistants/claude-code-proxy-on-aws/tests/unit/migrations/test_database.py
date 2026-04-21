"""Tests for migration database helpers."""

from __future__ import annotations

from migrations.database import build_connect_args, build_migration_database_url


def test_build_migration_database_url_uses_pg8000_without_ssl_query() -> None:
    url = build_migration_database_url(
        username="dbuser",
        password="p@ss:word",
        host="test-db.endpoint.rds.amazonaws.com",
    )

    assert url.startswith("postgresql+pg8000://dbuser:")
    assert "p%40ss%3Aword@" in url
    assert "test-db.endpoint.rds.amazonaws.com:5432/claude_proxy" in url
    assert "ssl=true" not in url


def test_build_connect_args_uses_ssl_context_for_pg8000() -> None:
    connect_args = build_connect_args("postgresql+pg8000://dbuser:dbpass@host:5432/claude_proxy")

    assert connect_args == {"ssl_context": True}


def test_build_connect_args_is_empty_for_other_drivers() -> None:
    connect_args = build_connect_args("postgresql+psycopg://dbuser:dbpass@host:5432/claude_proxy")

    assert connect_args == {}
