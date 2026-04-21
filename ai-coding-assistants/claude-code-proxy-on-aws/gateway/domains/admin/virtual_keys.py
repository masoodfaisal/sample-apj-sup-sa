"""Admin virtual key endpoints and service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from gateway.core.config import Settings
from gateway.core.dependencies import get_admin_virtual_key_service
from gateway.core.exceptions import NotFoundError
from shared.models import AuditEvent, VirtualKey
from shared.utils.constants import (
    AuditActorType,
    AuditEventType,
    AuditObjectType,
    VirtualKeyStatus,
)
from shared.utils.hashing import generate_api_key
from shared.utils.kms import KmsHelper

router = APIRouter(tags=["admin-virtual-keys"])


def _serialize_key(key: VirtualKey) -> dict[str, Any]:
    return {
        "id": str(key.id),
        "user_id": str(key.user_id),
        "status": key.status,
        "key_last4": key.key_last4,
        "issued_at": key.issued_at,
        "expires_at": key.expires_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
    }


class AdminVirtualKeyService:
    def __init__(
        self,
        key_repo,
        audit_repo,
        admin_ctx,
        session,
        settings: Settings,
    ) -> None:  # type: ignore[no-untyped-def]
        self._key_repo = key_repo
        self._audit_repo = audit_repo
        self._admin_ctx = admin_ctx
        self._session = session
        self._settings = settings

    def _calculate_expires_at(self, now: datetime) -> datetime | None:
        ttl = self._settings.virtual_key_ttl_ms
        return now + timedelta(milliseconds=ttl) if ttl > 0 else None

    async def list_keys(
        self, user_id: UUID | None, status: VirtualKeyStatus | None, page: int, page_size: int
    ) -> dict[str, Any]:
        items, next_page = await self._key_repo.list(
            user_id=user_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        return {"items": [_serialize_key(item) for item in items], "next_page": next_page}

    async def get_key(self, key_id: UUID) -> dict[str, Any]:
        key = await self._key_repo.get_by_id(key_id)
        if key is None:
            raise NotFoundError("Virtual key not found", code="virtual_key_not_found")
        return _serialize_key(key)

    async def rotate_key(self, key_id: UUID) -> dict[str, Any]:
        key = await self._key_repo.get_by_id(key_id)
        if key is None:
            raise NotFoundError("Virtual key not found", code="virtual_key_not_found")
        now = datetime.now(timezone.utc)
        await self._key_repo.update_status(
            key,
            VirtualKeyStatus.ROTATED,
            revoked_at=now,
        )
        plaintext = generate_api_key()
        new_key = await self._key_repo.create(
            VirtualKey(
                user_id=key.user_id,
                key_fingerprint=KmsHelper.generate_fingerprint(plaintext),
                key_last4=plaintext[-4:],
                kms_ciphertext=KmsHelper.encrypt_key(plaintext),
                status=VirtualKeyStatus.ACTIVE,
                issued_at=now,
                expires_at=self._calculate_expires_at(now),
                last_used_at=None,
                revoked_at=None,
            )
        )
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.VIRTUAL_KEY_ROTATED,
                object_type=AuditObjectType.VIRTUAL_KEY,
                object_id=str(key_id),
                request_id=self._admin_ctx.request_id,
                payload_json={"new_key_id": str(new_key.id)},
            )
        )
        await self._session.commit()
        return {
            "old_key_id": str(key_id),
            "new_key_id": str(new_key.id),
            "status": VirtualKeyStatus.ROTATED,
            "request_id": self._admin_ctx.request_id,
        }

    async def revoke_key(self, key_id: UUID) -> dict[str, Any]:
        key = await self._key_repo.get_by_id(key_id)
        if key is None:
            raise NotFoundError("Virtual key not found", code="virtual_key_not_found")
        await self._key_repo.update_status(
            key,
            VirtualKeyStatus.REVOKED,
            revoked_at=datetime.now(timezone.utc),
        )
        await self._audit_repo.create_event(
            AuditEvent(
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=self._admin_ctx.principal,
                event_type=AuditEventType.VIRTUAL_KEY_REVOKED,
                object_type=AuditObjectType.VIRTUAL_KEY,
                object_id=str(key_id),
                request_id=self._admin_ctx.request_id,
                payload_json={"status": VirtualKeyStatus.REVOKED},
            )
        )
        await self._session.commit()
        return {
            "key_id": str(key_id),
            "status": VirtualKeyStatus.REVOKED,
            "request_id": self._admin_ctx.request_id,
        }


@router.get("/virtual-keys")
async def list_virtual_keys(
    user_id: UUID | None = None,
    status: VirtualKeyStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    service=Depends(get_admin_virtual_key_service),  # type: ignore[assignment]
) -> dict[str, Any]:
    return await service.list_keys(user_id, status, page, page_size)


@router.get("/virtual-keys/{key_id}")
async def get_virtual_key(key_id: UUID, service=Depends(get_admin_virtual_key_service)):  # type: ignore[assignment]
    return await service.get_key(key_id)


@router.post("/virtual-keys/{key_id}/rotate")
async def rotate_virtual_key(key_id: UUID, service=Depends(get_admin_virtual_key_service)):  # type: ignore[assignment]
    return await service.rotate_key(key_id)


@router.post("/virtual-keys/{key_id}/revoke")
async def revoke_virtual_key(key_id: UUID, service=Depends(get_admin_virtual_key_service)):  # type: ignore[assignment]
    return await service.revoke_key(key_id)
