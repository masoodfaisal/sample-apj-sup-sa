"""Tests for schema validation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.models.user import User
from shared.schemas.model_catalog import ModelCreate, ModelUpdate
from shared.schemas.policy import BudgetPolicyCreate
from shared.schemas.user import UserResponse, UserUpdate
from shared.utils.constants import BudgetPeriod, ScopeType, UserStatus


def test_user_update_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        UserUpdate(status="INVALID")


def test_user_response_uses_from_attributes() -> None:
    user = User(
        id=uuid4(),
        identity_store_user_id="identity-id",
        user_name="alice",
        display_name="Alice",
        email="alice@example.com",
        status=UserStatus.ACTIVE.value,
        default_team_id=None,
        last_login_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    response = UserResponse.model_validate(user)

    assert response.status is UserStatus.ACTIVE


def test_budget_policy_create_accepts_enum_values() -> None:
    payload = BudgetPolicyCreate(
        scope_type=ScopeType.USER,
        scope_user_id=uuid4(),
        period=BudgetPeriod.DAILY,
        soft_limit_usd="10.00",
        hard_limit_usd="20.00",
    )

    assert payload.scope_type is ScopeType.USER
    assert payload.period is BudgetPeriod.DAILY


def test_model_create_accepts_optional_bedrock_region() -> None:
    payload = ModelCreate(
        canonical_name="glm-5",
        bedrock_model_id="zai.glm-5",
        bedrock_region="us-east-1",
        provider="zai",
    )

    assert payload.bedrock_region == "us-east-1"


def test_model_update_can_clear_bedrock_region() -> None:
    payload = ModelUpdate(bedrock_region=None)

    assert payload.bedrock_region is None
