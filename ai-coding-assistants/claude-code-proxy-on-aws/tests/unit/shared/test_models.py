"""Tests for ORM model metadata."""

from __future__ import annotations

from sqlalchemy import DateTime
from sqlalchemy.orm import configure_mappers

from shared.models import (
    Base,
    BudgetPolicy,
    IdentitySyncRun,
    ModelCatalog,
    ModelPricing,
    TeamMembership,
    UsageDailyAgg,
    UsageEvent,
    UsageMonthlyAgg,
    User,
    VirtualKey,
)


def test_all_expected_tables_are_registered() -> None:
    assert len(Base.metadata.tables) == 15
    assert "budget_policies" in Base.metadata.tables
    assert "usage_monthly_agg" in Base.metadata.tables


def test_mapper_configuration_is_valid() -> None:
    configure_mappers()


def test_default_team_is_stored_on_users() -> None:
    assert "default_team_id" in User.__table__.c
    assert "is_default" not in TeamMembership.__table__.c


def test_model_catalog_includes_optional_bedrock_region() -> None:
    assert "bedrock_region" in ModelCatalog.__table__.c
    assert ModelCatalog.__table__.c.bedrock_region.nullable is True


def test_budget_policy_has_active_uniqueness_indexes() -> None:
    index_names = {index.name for index in BudgetPolicy.__table__.indexes}
    assert "uq_budget_policies_user_active" in index_names
    assert "uq_budget_policies_team_active" in index_names


def test_usage_aggregates_use_surrogate_primary_keys() -> None:
    assert list(UsageDailyAgg.__table__.primary_key.columns.keys()) == ["id"]
    assert list(UsageMonthlyAgg.__table__.primary_key.columns.keys()) == ["id"]
    assert UsageDailyAgg.__table__.c.team_id.nullable is True
    assert UsageMonthlyAgg.__table__.c.team_id.nullable is True


def test_virtual_key_has_partial_unique_index() -> None:
    index_names = {index.name for index in VirtualKey.__table__.indexes}
    assert "uq_virtual_keys_active_user" in index_names


def test_datetime_columns_match_timezone_aware_schema() -> None:
    timezone_columns = [
        IdentitySyncRun.__table__.c.started_at,
        IdentitySyncRun.__table__.c.finished_at,
        User.__table__.c.last_synced_at,
        VirtualKey.__table__.c.issued_at,
        ModelPricing.__table__.c.effective_from,
        BudgetPolicy.__table__.c.window_started_at,
        UsageEvent.__table__.c.occurred_at,
        UsageDailyAgg.__table__.c.updated_at,
        UsageMonthlyAgg.__table__.c.updated_at,
    ]

    assert all(
        isinstance(column.type, DateTime) and column.type.timezone
        for column in timezone_columns
    )
