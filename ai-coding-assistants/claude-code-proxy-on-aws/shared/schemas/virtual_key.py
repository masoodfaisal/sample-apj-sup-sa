"""Virtual key DTOs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from shared.utils.constants import VirtualKeyStatus


class VirtualKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    key_fingerprint: str
    key_last4: str
    status: VirtualKeyStatus
    issued_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime
