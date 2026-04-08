"""User-related DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.utils.constants import MembershipRole, MembershipSource, UserStatus


class UserCreate(BaseModel):
    identity_store_user_id: str
    user_name: str
    display_name: str | None = None
    email: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: str | None = None
    status: UserStatus | None = None
    default_team_id: UUID | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    identity_store_user_id: str
    user_name: str
    display_name: str | None
    email: str | None
    status: UserStatus
    default_team_id: UUID | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TeamMembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    team_id: UUID
    source: MembershipSource
    role: MembershipRole
    created_at: datetime
    updated_at: datetime
