"""Auth token issuance request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class TokenIssuanceRequest(BaseModel):
    """Client metadata sent during token issuance."""

    client_name: str | None = None
    client_version: str | None = None
    aws_profile: str | None = None


class UserInfo(BaseModel):
    id: str
    identity_store_user_id: str
    display_name: str | None
    email: str | None
    default_team_id: str | None


class VirtualKeyInfo(BaseModel):
    id: str
    secret: str
    status: str
    issued_at: str
    expires_at: str | None


class TokenIssuanceResponse(BaseModel):
    user: UserInfo
    virtual_key: VirtualKeyInfo
