"""Tests for virtual key policy handler behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.handlers.virtual_key import VirtualKeyHandler
from gateway.domains.runtime.types import MessageRequest
from shared.exceptions import InvalidKeyError, KeyExpiredError, KeyRevokedError
from shared.utils.constants import VirtualKeyStatus


def _make_context() -> PolicyContext:
    return PolicyContext(
        api_key="test-key",
        request_id="req-1",
        request=MessageRequest(
            model="test-model",
            max_tokens=1,
            messages=[{"role": "user", "content": "hello"}],
        ),
    )


@pytest.mark.asyncio
async def test_active_unexpired_key_sets_policy_context() -> None:
    virtual_key = SimpleNamespace(
        status=VirtualKeyStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    handler = VirtualKeyHandler(
        repo=SimpleNamespace(get_by_fingerprint=AsyncMock(return_value=virtual_key))
    )
    context = _make_context()

    await handler.handle(context)

    assert context.virtual_key is virtual_key


@pytest.mark.asyncio
async def test_expired_active_key_raises_expired_error() -> None:
    virtual_key = SimpleNamespace(
        status=VirtualKeyStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    handler = VirtualKeyHandler(
        repo=SimpleNamespace(get_by_fingerprint=AsyncMock(return_value=virtual_key))
    )
    context = _make_context()

    with pytest.raises(KeyExpiredError):
        await handler.handle(context)


@pytest.mark.asyncio
async def test_non_active_key_raises_revoked_error() -> None:
    virtual_key = SimpleNamespace(
        status=VirtualKeyStatus.REVOKED,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    handler = VirtualKeyHandler(
        repo=SimpleNamespace(get_by_fingerprint=AsyncMock(return_value=virtual_key))
    )
    context = _make_context()

    with pytest.raises(KeyRevokedError):
        await handler.handle(context)


@pytest.mark.asyncio
async def test_missing_key_raises_invalid_key_error() -> None:
    handler = VirtualKeyHandler(
        repo=SimpleNamespace(get_by_fingerprint=AsyncMock(return_value=None))
    )
    context = _make_context()

    with pytest.raises(InvalidKeyError):
        await handler.handle(context)
