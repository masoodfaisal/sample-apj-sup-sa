"""Token issuance service."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gateway.core.config import Settings
from gateway.domains.auth.schemas import (
    TokenIssuanceRequest,
    TokenIssuanceResponse,
    UserInfo,
    VirtualKeyInfo,
)
from gateway.repositories.audit import AuditEventRepository
from gateway.repositories.user import UserRepository
from gateway.repositories.virtual_key import VirtualKeyRepository
from shared.exceptions import AuthenticationError, InternalError
from shared.models import AuditEvent, VirtualKey
from shared.utils.constants import (
    AuditActorType,
    AuditEventType,
    AuditObjectType,
    UserStatus,
    VirtualKeyStatus,
)
from shared.utils.hashing import generate_api_key
from shared.utils.kms import KmsHelper

logger = logging.getLogger("gateway.auth")
AUTHENTICATION_FAILED_MESSAGE = "Authentication failed"
INTERNAL_SERVER_ERROR_MESSAGE = "Internal server error"


class TokenIssuanceService:
    def __init__(
        self,
        user_repo: UserRepository,
        key_repo: VirtualKeyRepository,
        audit_repo: AuditEventRepository,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        self._user_repo = user_repo
        self._key_repo = key_repo
        self._audit_repo = audit_repo
        self._session = session
        self._settings = settings

    async def issue_token(
        self,
        principal_arn: str,
        request: TokenIssuanceRequest,
        request_id: str,
    ) -> TokenIssuanceResponse:
        session_name = self._extract_session_name(principal_arn)
        user = await self._resolve_active_user(session_name)
        plaintext_key, virtual_key = await self._get_or_create_key(
            user.id,
            principal_arn,
            request,
            request_id,
        )

        await self._session.commit()

        return TokenIssuanceResponse(
            user=UserInfo(
                id=str(user.id),
                identity_store_user_id=user.identity_store_user_id,
                display_name=user.display_name,
                email=user.email,
                default_team_id=str(user.default_team_id) if user.default_team_id else None,
            ),
            virtual_key=VirtualKeyInfo(
                id=str(virtual_key.id),
                secret=plaintext_key,
                status=virtual_key.status,
                issued_at=virtual_key.issued_at.isoformat(),
                expires_at=virtual_key.expires_at.isoformat() if virtual_key.expires_at else None,
            ),
        )

    @staticmethod
    def _extract_session_name(principal_arn: str) -> str:
        session_name = principal_arn.split("/")[-1]
        if not session_name:
            raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)
        return session_name

    async def _resolve_active_user(self, session_name: str):
        user = await self._user_repo.get_by_user_name(session_name)
        if user is None:
            user = await self._user_repo.get_by_identity_store_id(session_name)
        if user is None and "@" in session_name:
            user = await self._user_repo.get_by_email(session_name)
        if user is None or user.status != UserStatus.ACTIVE:
            raise AuthenticationError(AUTHENTICATION_FAILED_MESSAGE)
        return user

    @staticmethod
    def _reuse_key(virtual_key: VirtualKey) -> str:
        try:
            plaintext_key = KmsHelper.decrypt_key(virtual_key.kms_ciphertext)
        except Exception as exc:
            logger.exception("Failed to decrypt virtual key id=%s", virtual_key.id)
            raise InternalError(INTERNAL_SERVER_ERROR_MESSAGE) from exc
        virtual_key.last_used_at = datetime.now(timezone.utc)
        return plaintext_key

    def _calculate_expires_at(self, now: datetime) -> datetime | None:
        ttl = self._settings.virtual_key_ttl_ms
        return now + timedelta(milliseconds=ttl) if ttl > 0 else None

    @staticmethod
    def _is_expired(key: VirtualKey) -> bool:
        return key.expires_at is not None and key.expires_at <= datetime.now(timezone.utc)

    async def _record_issue_event(
        self,
        *,
        principal_arn: str,
        request: TokenIssuanceRequest,
        request_id: str,
        virtual_key: VirtualKey,
        now: datetime,
        refresh: bool,
    ) -> None:
        payload_json: dict[str, object] = {
            "client_name": request.client_name,
            "client_version": request.client_version,
            "aws_profile": request.aws_profile,
        }
        if refresh:
            payload_json["refresh"] = True

        await self._audit_repo.create_event(
            AuditEvent(
                id=uuid.uuid4(),
                actor_type=AuditActorType.IAM_PRINCIPAL,
                actor_id=principal_arn,
                event_type=AuditEventType.VIRTUAL_KEY_ISSUED,
                object_type=AuditObjectType.VIRTUAL_KEY,
                object_id=str(virtual_key.id),
                request_id=request_id,
                payload_json=payload_json,
                created_at=now,
            )
        )

    async def _get_or_create_key(
        self,
        user_id: uuid.UUID,
        principal_arn: str,
        request: TokenIssuanceRequest,
        request_id: str,
    ) -> tuple[str, VirtualKey]:
        existing_key = await self._key_repo.get_active_by_user(user_id, for_update=True)
        if existing_key is not None:
            if self._is_expired(existing_key):
                return await self._refresh_key_material(
                    existing_key,
                    principal_arn,
                    request,
                    request_id,
                )
            return self._reuse_key(existing_key), existing_key

        try:
            return await self._create_key(user_id, principal_arn, request, request_id)
        except IntegrityError as exc:
            await self._session.rollback()
            logger.warning(
                "Recovered from concurrent virtual key issuance user_id=%s request_id=%s",
                user_id,
                request_id,
            )
            existing_key = await self._key_repo.get_active_by_user(user_id, for_update=True)
            if existing_key is None:
                raise InternalError(INTERNAL_SERVER_ERROR_MESSAGE) from exc
            if self._is_expired(existing_key):
                return await self._refresh_key_material(
                    existing_key,
                    principal_arn,
                    request,
                    request_id,
                )
            return self._reuse_key(existing_key), existing_key

    async def _refresh_key_material(
        self,
        key: VirtualKey,
        principal_arn: str,
        request: TokenIssuanceRequest,
        request_id: str,
    ) -> tuple[str, VirtualKey]:
        plaintext_key = generate_api_key()
        now = datetime.now(timezone.utc)

        key.key_fingerprint = KmsHelper.generate_fingerprint(plaintext_key)
        key.key_last4 = plaintext_key[-4:]
        key.kms_ciphertext = KmsHelper.encrypt_key(plaintext_key)
        key.issued_at = now
        key.expires_at = self._calculate_expires_at(now)
        key.last_used_at = now
        key.revoked_at = None

        await self._session.flush()
        await self._record_issue_event(
            principal_arn=principal_arn,
            request=request,
            request_id=request_id,
            virtual_key=key,
            now=now,
            refresh=True,
        )
        return plaintext_key, key

    async def _create_key(
        self,
        user_id: uuid.UUID,
        principal_arn: str,
        request: TokenIssuanceRequest,
        request_id: str,
    ) -> tuple[str, VirtualKey]:
        plaintext_key = generate_api_key()
        now = datetime.now(timezone.utc)

        virtual_key = await self._key_repo.create(
            VirtualKey(
                id=uuid.uuid4(),
                user_id=user_id,
                key_fingerprint=KmsHelper.generate_fingerprint(plaintext_key),
                key_last4=plaintext_key[-4:],
                kms_ciphertext=KmsHelper.encrypt_key(plaintext_key),
                status=VirtualKeyStatus.ACTIVE,
                issued_at=now,
                expires_at=self._calculate_expires_at(now),
                last_used_at=now,
                revoked_at=None,
            )
        )
        await self._record_issue_event(
            principal_arn=principal_arn,
            request=request,
            request_id=request_id,
            virtual_key=virtual_key,
            now=now,
            refresh=False,
        )
        return plaintext_key, virtual_key
