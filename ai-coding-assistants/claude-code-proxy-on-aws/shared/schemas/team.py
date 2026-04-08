"""Team DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.utils.constants import TeamStatus


class TeamCreate(BaseModel):
    name: str
    description: str | None = None
    status: TeamStatus | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: TeamStatus | None = None


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    status: TeamStatus
    created_at: datetime
    updated_at: datetime
