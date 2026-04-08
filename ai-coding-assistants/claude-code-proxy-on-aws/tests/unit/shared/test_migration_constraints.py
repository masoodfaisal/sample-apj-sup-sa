"""Tests for migration-only constraints."""

import re
from pathlib import Path

MIGRATION_PATH = Path("migrations/versions/001_initial_schema.py")
MIGRATIONS_DIR = Path("migrations/versions")


def test_initial_migration_declares_all_tables() -> None:
    migration = MIGRATION_PATH.read_text()
    assert migration.count('op.create_table(') == 15


def test_initial_migration_includes_manual_indexes() -> None:
    migration = MIGRATION_PATH.read_text()
    assert "uq_budget_policies_user_active" in migration
    assert "uq_budget_policies_team_active" in migration
    assert "uq_usage_daily_agg_grain" in migration
    assert "uq_usage_monthly_agg_grain" in migration
    assert "coalesce(team_id" in migration


def test_migration_revision_ids_fit_alembic_version_column() -> None:
    revision_re = re.compile(r'^revision = "([^"]+)"$', re.MULTILINE)

    for migration_path in MIGRATIONS_DIR.glob("*.py"):
        revision = revision_re.search(migration_path.read_text())
        assert revision is not None, f"missing revision in {migration_path}"
        assert len(revision.group(1)) <= 32, f"revision too long in {migration_path}"
