"""Policy DTOs."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.utils.constants import BudgetPeriod, CachePolicy, ScopeType


class UserModelPolicyCreate(BaseModel):
    user_id: UUID
    model_id: UUID
    allow: bool
    cache_policy: CachePolicy | None = None
    max_tokens_override: int | None = None


class UserModelPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    model_id: UUID
    allow: bool
    cache_policy: CachePolicy | None
    max_tokens_override: int | None
    created_at: datetime
    updated_at: datetime


class TeamModelPolicyCreate(BaseModel):
    team_id: UUID
    model_id: UUID
    allow: bool
    cache_policy: CachePolicy | None = None
    max_tokens_override: int | None = None


class TeamModelPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    model_id: UUID
    allow: bool
    cache_policy: CachePolicy | None
    max_tokens_override: int | None
    created_at: datetime
    updated_at: datetime


class BudgetPolicyCreate(BaseModel):
    scope_type: ScopeType
    scope_user_id: UUID | None = None
    scope_team_id: UUID | None = None
    model_id: UUID | None = None
    period: BudgetPeriod
    soft_limit_usd: Decimal
    hard_limit_usd: Decimal
    currency: str = "USD"
    active: bool = True


class BudgetPolicyUpdate(BaseModel):
    model_id: UUID | None = None
    soft_limit_usd: Decimal | None = None
    hard_limit_usd: Decimal | None = None
    currency: str | None = None
    active: bool | None = None


class BudgetPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scope_type: ScopeType
    scope_user_id: UUID | None
    scope_team_id: UUID | None
    model_id: UUID | None
    period: BudgetPeriod
    soft_limit_usd: Decimal
    hard_limit_usd: Decimal
    current_used_usd: Decimal
    window_started_at: datetime
    currency: str
    active: bool
    created_at: datetime
    updated_at: datetime
