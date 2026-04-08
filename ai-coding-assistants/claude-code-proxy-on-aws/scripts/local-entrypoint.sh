#!/bin/sh
set -eu

home_dir="${HOME:-/tmp/app-home}"
aws_source_dir="${AWS_CONFIG_SOURCE_DIR:-}"

mkdir -p "$home_dir"

if [ -n "$aws_source_dir" ] && [ -d "$aws_source_dir" ]; then
    rm -rf "$home_dir/.aws"
    mkdir -p "$home_dir/.aws"
    cp -R "$aws_source_dir"/. "$home_dir/.aws"/
fi

# Ensure local bootstrap and runtime import the source tree under /app first.
export PYTHONPATH="/app${PYTHONPATH:+:$PYTHONPATH}"

python - <<'PY'
import os
import socket
import time
from sqlalchemy.engine import make_url

database_url = os.environ["DATABASE_URL"]
url = make_url(database_url)
host = url.host or "postgres"
port = url.port or 5432

for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=1):
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"database not reachable: {host}:{port}")
PY

if [ -n "${DATABASE_URL:-}" ]; then
    migration_database_url="$(printf '%s' "$DATABASE_URL" | sed 's/postgresql+asyncpg/postgresql+pg8000/')"
    if MIGRATION_DATABASE_URL="$migration_database_url" MIGRATION_DISABLE_SSL=true python - <<'PY'
from __future__ import annotations

import os

from sqlalchemy import create_engine, text

database_url = os.environ["MIGRATION_DATABASE_URL"]
engine = create_engine(database_url)

with engine.connect() as conn:
    alembic_version_exists = conn.execute(
        text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
    ).scalar_one()
    teams_exists = conn.execute(
        text("SELECT to_regclass('public.teams') IS NOT NULL")
    ).scalar_one()

if teams_exists and not alembic_version_exists:
    raise SystemExit(10)
PY
    then
        stamp_status=0
    else
        stamp_status=$?
    fi
    if [ "$stamp_status" -eq 10 ]; then
        MIGRATION_DISABLE_SSL=true DATABASE_URL="$migration_database_url" python -m alembic -c migrations/alembic.ini stamp 001_initial_schema
    elif [ "$stamp_status" -ne 0 ]; then
        exit "$stamp_status"
    fi
    MIGRATION_DISABLE_SSL=true DATABASE_URL="$migration_database_url" python -m alembic -c migrations/alembic.ini upgrade head
fi

python /app/scripts/local-bootstrap.py
export ADMIN_ORIGIN_ENFORCE="${ADMIN_ORIGIN_ENFORCE:-false}"
export ENVIRONMENT="${ENVIRONMENT:-local}"
exec uvicorn gateway.main:app --host 0.0.0.0 --port "${PORT:-8000}"
