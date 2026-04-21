"""Audit DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.utils.constants import SyncRunStatus


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_type: str
    actor_id: str
    event_type: str
    object_type: str
    object_id: str
    request_id: str | None
    sync_run_id: UUID | None
    payload_json: dict[str, object] | None
    created_at: datetime


class SyncRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime
    finished_at: datetime | None
    status: SyncRunStatus
    users_scanned: int
    users_created: int
    users_updated: int
    users_inactivated: int
    error_summary: str | None
    created_at: datetime


class SyncRunTriggerResponse(BaseModel):
    sync_run_id: UUID
    status: SyncRunStatus
    sync_scope: Literal["USERS_ONLY"]
    users_scanned: int
    users_created: int
    users_updated: int
    users_inactivated: int
