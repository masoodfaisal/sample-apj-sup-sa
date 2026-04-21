"""Virtual key validation handler."""

from __future__ import annotations

from datetime import datetime, timezone

from gateway.core.exceptions import InvalidKeyError, KeyExpiredError, KeyRevokedError
from gateway.domains.policy.context import PolicyContext
from gateway.domains.policy.engine import HandlerType
from gateway.repositories import VirtualKeyRepository
from shared.utils.constants import VirtualKeyStatus
from shared.utils.hashing import sha256_hex


class VirtualKeyHandler:
    handler_type = HandlerType.VIRTUAL_KEY

    def __init__(self, repo: VirtualKeyRepository) -> None:
        self._repo = repo

    async def handle(self, context: PolicyContext) -> None:
        fingerprint = sha256_hex(context.api_key)
        virtual_key = await self._repo.get_by_fingerprint(fingerprint)
        if virtual_key is None:
            raise InvalidKeyError()
        if virtual_key.status == VirtualKeyStatus.EXPIRED:
            raise KeyExpiredError()
        if virtual_key.status != VirtualKeyStatus.ACTIVE:
            raise KeyRevokedError()
        if virtual_key.expires_at is not None and virtual_key.expires_at <= datetime.now(timezone.utc):
            raise KeyExpiredError()
        context.virtual_key = virtual_key
