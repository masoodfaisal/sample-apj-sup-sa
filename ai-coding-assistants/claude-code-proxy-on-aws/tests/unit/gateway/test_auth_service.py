"""Tests for auth token issuance service behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from gateway.core.config import Settings
from gateway.domains.auth.schemas import TokenIssuanceRequest
from gateway.domains.auth.service import TokenIssuanceService
from shared.exceptions import AuthenticationError, InternalError
from shared.utils.constants import UserStatus, VirtualKeyStatus


def _build_service(
    *,
    user_repo,
    key_repo,
    audit_repo=None,
    session=None,
    settings=None,
) -> TokenIssuanceService:
    return TokenIssuanceService(
        user_repo=user_repo,
        key_repo=key_repo,
        audit_repo=audit_repo or SimpleNamespace(create_event=AsyncMock()),
        session=session or SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), flush=AsyncMock()),
        settings=settings or Settings(),
    )


def _build_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        identity_store_user_id="identity-user",
        display_name="Alice",
        email="alice@example.com",
        default_team_id=None,
        status=UserStatus.ACTIVE,
    )


def _build_user_repo(user: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        get_by_user_name=AsyncMock(return_value=user),
        get_by_identity_store_id=AsyncMock(return_value=None),
        get_by_email=AsyncMock(return_value=None),
    )


@pytest.mark.asyncio
async def test_issue_token_recovers_from_concurrent_active_key_creation() -> None:
    user = _build_user()
    existing_key = SimpleNamespace(
        id=uuid4(),
        kms_ciphertext=b"ciphertext",
        status=VirtualKeyStatus.ACTIVE,
        issued_at=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc),
        expires_at=None,
        last_used_at=None,
    )
    user_repo = _build_user_repo(user)
    key_repo = SimpleNamespace(
        get_active_by_user=AsyncMock(side_effect=[None, existing_key]),
        create=AsyncMock(
            side_effect=IntegrityError("insert into virtual_keys", {"user_id": str(user.id)}, None)
        ),
    )
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    service = _build_service(user_repo=user_repo, key_repo=key_repo, session=session)

    with patch(
        "gateway.domains.auth.service.KmsHelper.decrypt_key",
        return_value="vk-secret",
    ), patch(
        "gateway.domains.auth.service.KmsHelper.encrypt_key",
        return_value=b"encrypted",
    ), patch(
        "gateway.domains.auth.service.KmsHelper.generate_fingerprint",
        return_value="fingerprint",
    ):
        response = await service.issue_token(
            "arn:aws:sts::123456789012:assumed-role/GatewayAuth/alice",
            TokenIssuanceRequest(client_name="claude-code"),
            "req-auth-race",
        )

    assert session.rollback.await_count == 1
    assert session.commit.await_count == 1
    assert response.user.id == str(user.id)
    assert response.virtual_key.id == str(existing_key.id)
    assert response.virtual_key.secret == "vk-secret"
    assert existing_key.last_used_at is not None


@pytest.mark.asyncio
async def test_issue_token_sets_expires_at_from_ttl_on_new_key() -> None:
    user = _build_user()
    user_repo = _build_user_repo(user)

    async def create_key(key):  # type: ignore[no-untyped-def]
        return key

    key_repo = SimpleNamespace(
        get_active_by_user=AsyncMock(return_value=None),
        create=AsyncMock(side_effect=create_key),
    )
    audit_repo = SimpleNamespace(create_event=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), flush=AsyncMock())
    service = _build_service(
        user_repo=user_repo,
        key_repo=key_repo,
        audit_repo=audit_repo,
        session=session,
        settings=Settings(virtual_key_ttl_ms=3_600_000),
    )

    before_call = datetime.now(timezone.utc)
    with patch("gateway.domains.auth.service.generate_api_key", return_value="vk-new-secret"), patch(
        "gateway.domains.auth.service.KmsHelper.encrypt_key",
        return_value=b"encrypted",
    ), patch(
        "gateway.domains.auth.service.KmsHelper.generate_fingerprint",
        return_value="fingerprint-new",
    ):
        response = await service.issue_token(
            "arn:aws:sts::123456789012:assumed-role/GatewayAuth/alice",
            TokenIssuanceRequest(client_name="claude-code", client_version="1.0.0"),
            "req-auth-new",
        )
    after_call = datetime.now(timezone.utc)

    created_key = key_repo.create.await_args.args[0]
    assert created_key.expires_at is not None
    assert before_call <= created_key.issued_at <= after_call
    assert created_key.expires_at > after_call
    ttl_seconds = (created_key.expires_at - created_key.issued_at).total_seconds()
    assert 3595 <= ttl_seconds <= 3605
    assert response.virtual_key.expires_at == created_key.expires_at.isoformat()
    assert audit_repo.create_event.await_args.args[0].payload_json == {
        "client_name": "claude-code",
        "client_version": "1.0.0",
        "aws_profile": None,
    }


@pytest.mark.asyncio
async def test_issue_token_reuses_unexpired_active_key() -> None:
    user = _build_user()
    user_repo = _build_user_repo(user)
    existing_key = SimpleNamespace(
        id=uuid4(),
        kms_ciphertext=b"ciphertext",
        status=VirtualKeyStatus.ACTIVE,
        issued_at=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc),
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        last_used_at=None,
    )
    key_repo = SimpleNamespace(
        get_active_by_user=AsyncMock(return_value=existing_key),
        create=AsyncMock(),
    )
    service = _build_service(user_repo=user_repo, key_repo=key_repo)

    with patch("gateway.domains.auth.service.KmsHelper.decrypt_key", return_value="vk-existing"):
        response = await service.issue_token(
            "arn:aws:sts::123456789012:assumed-role/GatewayAuth/alice",
            TokenIssuanceRequest(client_name="claude-code"),
            "req-auth-reuse",
        )

    assert response.virtual_key.id == str(existing_key.id)
    assert response.virtual_key.secret == "vk-existing"
    assert existing_key.last_used_at is not None
    key_repo.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_issue_token_refreshes_expired_active_key_in_place() -> None:
    user = _build_user()
    user_repo = _build_user_repo(user)
    existing_key = SimpleNamespace(
        id=uuid4(),
        kms_ciphertext=b"old-ciphertext",
        key_fingerprint="old-fingerprint",
        key_last4="1111",
        status=VirtualKeyStatus.ACTIVE,
        issued_at=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc),
        expires_at=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
        last_used_at=datetime(2026, 4, 5, 9, 30, tzinfo=timezone.utc),
        revoked_at=None,
    )
    key_repo = SimpleNamespace(
        get_active_by_user=AsyncMock(return_value=existing_key),
        create=AsyncMock(),
    )
    audit_repo = SimpleNamespace(create_event=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), flush=AsyncMock())
    service = _build_service(
        user_repo=user_repo,
        key_repo=key_repo,
        audit_repo=audit_repo,
        session=session,
        settings=Settings(virtual_key_ttl_ms=7_200_000),
    )

    with patch("gateway.domains.auth.service.generate_api_key", return_value="vk-refreshed"), patch(
        "gateway.domains.auth.service.KmsHelper.encrypt_key",
        return_value=b"new-ciphertext",
    ), patch(
        "gateway.domains.auth.service.KmsHelper.generate_fingerprint",
        return_value="new-fingerprint",
    ):
        response = await service.issue_token(
            "arn:aws:sts::123456789012:assumed-role/GatewayAuth/alice",
            TokenIssuanceRequest(client_name="claude-code", aws_profile="dev"),
            "req-auth-refresh",
        )

    assert response.virtual_key.id == str(existing_key.id)
    assert response.virtual_key.secret == "vk-refreshed"
    assert existing_key.key_fingerprint == "new-fingerprint"
    assert existing_key.key_last4 == "shed"
    assert existing_key.kms_ciphertext == b"new-ciphertext"
    assert existing_key.status == VirtualKeyStatus.ACTIVE
    assert existing_key.expires_at is not None
    assert existing_key.issued_at == existing_key.last_used_at
    assert session.flush.await_count == 1
    key_repo.create.assert_not_awaited()

    event = audit_repo.create_event.await_args.args[0]
    assert event.object_id == str(existing_key.id)
    assert event.payload_json == {
        "client_name": "claude-code",
        "client_version": None,
        "aws_profile": "dev",
        "refresh": True,
    }


@pytest.mark.asyncio
async def test_issue_token_refreshes_expired_key_without_new_expiry_when_ttl_is_zero() -> None:
    user = _build_user()
    user_repo = _build_user_repo(user)
    existing_key = SimpleNamespace(
        id=uuid4(),
        kms_ciphertext=b"old-ciphertext",
        key_fingerprint="old-fingerprint",
        key_last4="1111",
        status=VirtualKeyStatus.ACTIVE,
        issued_at=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc),
        expires_at=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
        last_used_at=datetime(2026, 4, 5, 9, 30, tzinfo=timezone.utc),
        revoked_at=None,
    )
    key_repo = SimpleNamespace(
        get_active_by_user=AsyncMock(return_value=existing_key),
        create=AsyncMock(),
    )
    service = _build_service(
        user_repo=user_repo,
        key_repo=key_repo,
        settings=Settings(virtual_key_ttl_ms=0),
    )

    with patch("gateway.domains.auth.service.generate_api_key", return_value="vk-ttl-zero"), patch(
        "gateway.domains.auth.service.KmsHelper.encrypt_key",
        return_value=b"cipher-zero",
    ), patch(
        "gateway.domains.auth.service.KmsHelper.generate_fingerprint",
        return_value="fingerprint-zero",
    ):
        response = await service.issue_token(
            "arn:aws:sts::123456789012:assumed-role/GatewayAuth/alice",
            TokenIssuanceRequest(client_name="claude-code"),
            "req-auth-refresh-zero",
        )

    assert existing_key.expires_at is None
    assert response.virtual_key.expires_at is None


@pytest.mark.asyncio
async def test_resolve_active_user_returns_generic_auth_failure_for_missing_user() -> None:
    user_repo = SimpleNamespace(
        get_by_user_name=AsyncMock(return_value=None),
        get_by_identity_store_id=AsyncMock(return_value=None),
        get_by_email=AsyncMock(return_value=None),
    )
    service = _build_service(user_repo=user_repo, key_repo=SimpleNamespace())

    with pytest.raises(AuthenticationError, match="Authentication failed"):
        await service._resolve_active_user("missing@example.com")


@pytest.mark.asyncio
async def test_resolve_active_user_returns_generic_auth_failure_for_inactive_user() -> None:
    user_repo = SimpleNamespace(
        get_by_user_name=AsyncMock(
            return_value=SimpleNamespace(id=uuid4(), status=UserStatus.INACTIVE)
        ),
        get_by_identity_store_id=AsyncMock(return_value=None),
        get_by_email=AsyncMock(return_value=None),
    )
    service = _build_service(user_repo=user_repo, key_repo=SimpleNamespace())

    with pytest.raises(AuthenticationError, match="Authentication failed"):
        await service._resolve_active_user("inactive-user")


def test_reuse_key_hides_decrypt_failure_details() -> None:
    with patch(
        "gateway.domains.auth.service.KmsHelper.decrypt_key",
        side_effect=ValueError("kms decrypt failed"),
    ):
        with pytest.raises(InternalError, match="Internal server error"):
            TokenIssuanceService._reuse_key(
                SimpleNamespace(id=uuid4(), kms_ciphertext=b"ciphertext")
            )
