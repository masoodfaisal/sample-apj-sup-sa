#!/bin/sh
set -e
export DATABASE_URL="postgresql+pg8000://${DB_USERNAME}:${DB_PASSWORD}@${DB_ENDPOINT}:5432/claude_proxy"
exec python -m alembic -c migrations/alembic.ini upgrade head
